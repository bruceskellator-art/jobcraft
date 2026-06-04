"""LLM field-mapping agent for the Apply Engine.

SAFETY INVARIANTS (enforced in code, not just comments):
1. Knockout fields are ONLY filled from profile_fields.
   If the profile value is missing, the field is left with value=None,
   source="none", confidence=0.0.  The LLM is NEVER called to invent a value.
2. Only approved answer_bank rows are used (enforced by find_similar_answer).
3. Free-text generation (e.g. "why this role") uses the cover letter corpus;
   the LLM is invoked only for non-knockout, non-structured fields.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.apply.types import KNOCKOUT_KEYS, FieldMap, FormField, MappedField
from app.embeddings.base import EmbeddingClient
from app.repositories.profile_field import ProfileFieldRepository
from app.services.answer_bank_match import find_similar_answer
from app.vectorstore.base import VectorStore

if TYPE_CHECKING:
    from app.db.models.job_posting import JobPosting
    from app.llm.client import LLMClient

logger = logging.getLogger(__name__)

# Confidence values for each resolution path.
_CONFIDENCE_PROFILE = 1.0
_CONFIDENCE_ANSWER_BANK = 0.9
_CONFIDENCE_COVER_LETTER = 0.7
_CONFIDENCE_GENERATED = 0.6
_CONFIDENCE_NONE = 0.0

# Profile keys that indicate free-text "why this role/company" questions.
_WHY_ROLE_LABELS = frozenset(
    {
        "why this role",
        "why this company",
        "why do you want to work here",
        "why are you interested",
        "what interests you",
        "cover letter",
        "motivation",
    }
)


def _is_knockout(field: FormField) -> bool:
    """Return True if the field is a knockout field by flag or canonical key."""
    return field.is_knockout or field.name.lower() in KNOCKOUT_KEYS


def _lookup_profile(
    profile_map: dict[str, str],
    field: FormField,
) -> str | None:
    """Attempt a deterministic match of field.name or field.label against profile keys."""
    # Try exact key match first.
    key = field.name.lower()
    if key in profile_map:
        return profile_map[key]
    # Try normalised label.
    label_key = field.label.lower().replace(" ", "_")
    if label_key in profile_map:
        return profile_map[label_key]
    return None


def _is_why_role_field(field: FormField) -> bool:
    label_lower = field.label.lower()
    return any(phrase in label_lower for phrase in _WHY_ROLE_LABELS)


async def _generate_why_role(
    llm: LLMClient | None,
    field: FormField,
    job: JobPosting,
    cover_letter: str | None,
) -> tuple[str | None, float]:
    """Generate a free-text 'why this role' answer using the cover letter corpus.

    Returns (value, confidence). If no LLM is provided or cover_letter is
    absent, returns (None, 0.0).
    """
    if llm is None or not cover_letter:
        return None, _CONFIDENCE_NONE

    # We synthesise a lightweight prompt directly; no PromptVersion needed for
    # this inline call.  In a full implementation this would use a versioned
    # prompt.  For now we derive an answer from the cover letter text.
    excerpt = cover_letter[:800]  # keep tokens low
    value = (
        f"Based on my background and interest in {job.company}, "
        f"I am excited about this {job.title} role. {excerpt[:200]}"
    )
    return value, _CONFIDENCE_COVER_LETTER


async def map_fields(
    session: AsyncSession,
    llm: LLMClient | None,
    embed: EmbeddingClient,
    store: VectorStore,
    user_id: uuid.UUID,
    job: JobPosting,
    fields: list[FormField],
    *,
    cover_letter: str | None = None,
) -> FieldMap:
    """Map each FormField to a value, drawing on profile, answer_bank, and cover letter.

    Safety invariants (enforced):
    - Knockout fields: value from profile only; if absent → None/confidence=0.
    - Answer bank: only approved rows (find_similar_answer guarantee).
    - No LLM invocation for knockout fields.
    """
    repo = ProfileFieldRepository(session)
    profile_fields = await repo.list_by_user(user_id)
    profile_map: dict[str, str] = {pf.key.lower(): pf.value for pf in profile_fields}

    mapped: list[MappedField] = []

    for field in fields:
        if _is_knockout(field):
            # SAFETY RULE: knockout fields come ONLY from profile_fields.
            value = _lookup_profile(profile_map, field)
            if value is not None:
                mapped.append(
                    MappedField(
                        field=field,
                        value=value,
                        source="profile",
                        confidence=_CONFIDENCE_PROFILE,
                    )
                )
            else:
                logger.warning(
                    "Knockout field '%s' has no profile value for user %s — "
                    "leaving unfilled (will force REVIEW).",
                    field.name,
                    user_id,
                )
                mapped.append(
                    MappedField(
                        field=field,
                        value=None,
                        source="none",
                        confidence=_CONFIDENCE_NONE,
                    )
                )
            continue

        # Non-knockout: try profile first (deterministic).
        profile_value = _lookup_profile(profile_map, field)
        if profile_value is not None:
            mapped.append(
                MappedField(
                    field=field,
                    value=profile_value,
                    source="profile",
                    confidence=_CONFIDENCE_PROFILE,
                )
            )
            continue

        # Try approved answer bank for screening questions.
        answer = await find_similar_answer(
            session,
            embed,
            store,
            user_id,
            field.label,
        )
        if answer is not None:
            mapped.append(
                MappedField(
                    field=field,
                    value=answer.answer,
                    source="answer_bank",
                    confidence=_CONFIDENCE_ANSWER_BANK,
                )
            )
            continue

        # Free-text "why this role" questions — use cover letter corpus / LLM.
        if _is_why_role_field(field):
            value, confidence = await _generate_why_role(llm, field, job, cover_letter)
            if value is not None:
                mapped.append(
                    MappedField(
                        field=field,
                        value=value,
                        source="cover_letter",
                        confidence=confidence,
                    )
                )
                continue

        # No source resolved — leave unfilled.
        mapped.append(
            MappedField(
                field=field,
                value=None,
                source="none",
                confidence=_CONFIDENCE_NONE,
            )
        )

    return FieldMap(fields=mapped)
