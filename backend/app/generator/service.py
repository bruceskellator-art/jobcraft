"""Generator service: grounded resume and cover-letter generation.

Prompt ensure_* helpers use the savepoint pattern from matcher/service.py:
speculative insert inside begin_nested(); on IntegrityError roll back only
the savepoint and re-select the already-inserted row.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.experience_item import ExperienceItem
from app.db.models.job_posting import JobPosting
from app.db.models.match import Match
from app.db.models.prompt_version import PromptVersion
from app.embeddings.base import EmbeddingClient
from app.generator.types import (
    ArtifactScores,
    GeneratedDoc,
    GroundednessResult,
    StyleConfig,
)
from app.llm.client import LLMClient
from app.services.embed_pipeline import COLLECTION_USER_EXPERIENCE, _compose_jd_text
from app.vectorstore.base import VectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt constants
# ---------------------------------------------------------------------------

_RESUME_PROMPT_NAME = "generate_resume_v1"
_RESUME_PROMPT_VERSION = 1
_RESUME_PROMPT_MODEL = "claude-sonnet-4-6"
_RESUME_PROMPT_TEMPERATURE = 0.3
_RESUME_PROMPT_TEMPLATE = """\
You are a professional resume writer. Your job is to produce a tailored, \
grounded Markdown resume.

STRICT RULES:
- Use ONLY facts stated in <experience>. Never invent roles, dates, skills, or metrics.
- Tailor every bullet's framing toward the requirements in <job>.
- Return valid Markdown only. No prose outside the document. No code fences.
- Tone: {{ tone }}. Target length: {{ length }}.
{% if emphasis %}- Emphasise these areas: {{ emphasis }}.{% endif %}

<experience>
{{ experience_items }}
</experience>

<job>
{{ job_description }}
</job>
"""

_COVER_LETTER_PROMPT_NAME = "generate_cover_letter_v1"
_COVER_LETTER_PROMPT_VERSION = 1
_COVER_LETTER_PROMPT_MODEL = "claude-sonnet-4-6"
_COVER_LETTER_PROMPT_TEMPERATURE = 0.4
_COVER_LETTER_PROMPT_TEMPLATE = """\
You are a professional cover letter writer. Produce a tailored, grounded \
Markdown cover letter.

STRICT RULES:
- Use ONLY facts stated in <experience>. Never invent anything.
- Explain WHY THIS COMPANY using <culture_signals>.
- Explain WHY THIS ROLE using <responsibilities>.
- Include exactly ONE concrete story from <experience> that maps to the role.
- Return valid Markdown only. No prose outside the document. No code fences.
- Tone: {{ tone }}.

<experience>
{{ experience_items }}
</experience>

<responsibilities>
{{ responsibilities }}
</responsibilities>

<culture_signals>
{{ culture_signals }}
</culture_signals>

<job>
{{ job_description }}
</job>
"""

_GROUNDEDNESS_PROMPT_NAME = "groundedness_check_v1"
_GROUNDEDNESS_PROMPT_VERSION = 1
_GROUNDEDNESS_PROMPT_MODEL = "claude-sonnet-4-6"
_GROUNDEDNESS_PROMPT_TEMPERATURE = 0.0
_GROUNDEDNESS_PROMPT_TEMPLATE = """\
You are an anti-hallucination judge. Given a resume/cover-letter and a set of \
experience items, identify every factual claim in the document and map each \
claim to the experience item that supports it.

Return ONLY a JSON object — no prose, no fences — matching this schema exactly:
{
  "claims": [
    {
      "text": "<verbatim claim text>",
      "experience_id": "<uuid of supporting experience item, or null>",
      "grounded": <true if experience_id is non-null, else false>
    }
  ],
  "grounded_ratio": <float 0..1, share of claims where grounded=true>,
  "ungrounded": ["<claim text for every claim where grounded=false>"]
}

<document>
{{ document }}
</document>

<experience_items>
{{ experience_items }}
</experience_items>
"""


# ---------------------------------------------------------------------------
# Savepoint-pattern prompt helpers
# ---------------------------------------------------------------------------


async def ensure_resume_prompt(session: AsyncSession) -> PromptVersion:
    """Return (or create) the active generate_resume_v1 PromptVersion."""
    result = await session.execute(
        select(PromptVersion).where(
            PromptVersion.name == _RESUME_PROMPT_NAME,
            PromptVersion.is_active == True,  # noqa: E712
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    prompt = PromptVersion(
        name=_RESUME_PROMPT_NAME,
        version=_RESUME_PROMPT_VERSION,
        template=_RESUME_PROMPT_TEMPLATE,
        model=_RESUME_PROMPT_MODEL,
        temperature=_RESUME_PROMPT_TEMPERATURE,
        is_active=True,
    )
    try:
        async with session.begin_nested():
            session.add(prompt)
            await session.flush()
            await session.refresh(prompt)
    except IntegrityError:
        result = await session.execute(
            select(PromptVersion).where(
                PromptVersion.name == _RESUME_PROMPT_NAME,
                PromptVersion.is_active == True,  # noqa: E712
            )
        )
        prompt = result.scalar_one()
    return prompt


async def ensure_cover_letter_prompt(session: AsyncSession) -> PromptVersion:
    """Return (or create) the active generate_cover_letter_v1 PromptVersion."""
    result = await session.execute(
        select(PromptVersion).where(
            PromptVersion.name == _COVER_LETTER_PROMPT_NAME,
            PromptVersion.is_active == True,  # noqa: E712
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    prompt = PromptVersion(
        name=_COVER_LETTER_PROMPT_NAME,
        version=_COVER_LETTER_PROMPT_VERSION,
        template=_COVER_LETTER_PROMPT_TEMPLATE,
        model=_COVER_LETTER_PROMPT_MODEL,
        temperature=_COVER_LETTER_PROMPT_TEMPERATURE,
        is_active=True,
    )
    try:
        async with session.begin_nested():
            session.add(prompt)
            await session.flush()
            await session.refresh(prompt)
    except IntegrityError:
        result = await session.execute(
            select(PromptVersion).where(
                PromptVersion.name == _COVER_LETTER_PROMPT_NAME,
                PromptVersion.is_active == True,  # noqa: E712
            )
        )
        prompt = result.scalar_one()
    return prompt


async def ensure_groundedness_prompt(session: AsyncSession) -> PromptVersion:
    """Return (or create) the active groundedness_check_v1 PromptVersion."""
    result = await session.execute(
        select(PromptVersion).where(
            PromptVersion.name == _GROUNDEDNESS_PROMPT_NAME,
            PromptVersion.is_active == True,  # noqa: E712
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    prompt = PromptVersion(
        name=_GROUNDEDNESS_PROMPT_NAME,
        version=_GROUNDEDNESS_PROMPT_VERSION,
        template=_GROUNDEDNESS_PROMPT_TEMPLATE,
        model=_GROUNDEDNESS_PROMPT_MODEL,
        temperature=_GROUNDEDNESS_PROMPT_TEMPERATURE,
        is_active=True,
    )
    try:
        async with session.begin_nested():
            session.add(prompt)
            await session.flush()
            await session.refresh(prompt)
    except IntegrityError:
        result = await session.execute(
            select(PromptVersion).where(
                PromptVersion.name == _GROUNDEDNESS_PROMPT_NAME,
                PromptVersion.is_active == True,  # noqa: E712
            )
        )
        prompt = result.scalar_one()
    return prompt


# ---------------------------------------------------------------------------
# RAG retrieval
# ---------------------------------------------------------------------------


async def _retrieve_relevant_experience(
    session: AsyncSession,
    embed: EmbeddingClient,
    store: VectorStore,
    user_id: uuid.UUID,
    job: JobPosting,
    top_n: int = 12,
) -> list[ExperienceItem]:
    """RAG: retrieve the most relevant experience items for a job.

    Embeds the JD, vector-searches the user's indexed corpus, then loads
    the matching ExperienceItems by id in rank order.

    Falls back to ALL experience items if:
    - the vector store has no indexed vectors for this user, OR
    - fewer than top_n items are found in the store.
    """
    jd_text = _compose_jd_text(job)
    jd_vectors = await embed.embed([jd_text])
    jd_vec = jd_vectors[0]

    scored = await store.search(
        COLLECTION_USER_EXPERIENCE,
        jd_vec,
        top_k=top_n,
        payload_filter={"user_id": str(user_id)},
    )

    if not scored:
        logger.debug(
            "_retrieve_relevant_experience: no vectors for user %s, loading all items",
            user_id,
        )
        result = await session.execute(
            select(ExperienceItem).where(ExperienceItem.user_id == user_id)
        )
        return list(result.scalars().all())

    # Load items in rank order, skipping any ids not found in the DB.
    ids_in_rank = [uuid.UUID(sp.id) for sp in scored]
    result = await session.execute(
        select(ExperienceItem).where(ExperienceItem.id.in_(ids_in_rank))
    )
    by_id = {item.id: item for item in result.scalars().all()}
    return [by_id[i] for i in ids_in_rank if i in by_id]


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_experience_items(items: list[ExperienceItem]) -> str:
    return "\n\n".join(
        f"{idx + 1}. [{item.kind}] {item.title or '(untitled)'} "
        f"(id={item.id})\n{item.content}"
        for idx, item in enumerate(items)
    )


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


async def generate_resume(
    session: AsyncSession,
    llm: LLMClient,
    embed: EmbeddingClient,
    store: VectorStore,
    user_id: uuid.UUID,
    job: JobPosting,
    style: StyleConfig,
) -> str:
    """Generate a grounded Markdown resume tailored to a job posting.

    Returns raw Markdown; does NOT persist to the database.
    """
    items = await _retrieve_relevant_experience(session, embed, store, user_id, job)
    prompt = await ensure_resume_prompt(session)

    response = await llm.complete(
        prompt.id,
        inputs={
            "experience_items": _format_experience_items(items),
            "job_description": _compose_jd_text(job),
            "tone": style.tone,
            "length": style.length,
            "emphasis": ", ".join(style.emphasis) if style.emphasis else "",
        },
        response_model=GeneratedDoc,
    )
    if response.parsed is None:
        raise RuntimeError("generate_resume: LLM returned no parsed result")
    return response.parsed.markdown


async def generate_cover_letter(
    session: AsyncSession,
    llm: LLMClient,
    embed: EmbeddingClient,
    store: VectorStore,
    user_id: uuid.UUID,
    job: JobPosting,
    style: StyleConfig,
) -> str:
    """Generate a grounded Markdown cover letter tailored to a job posting.

    Returns raw Markdown; does NOT persist to the database.
    """
    items = await _retrieve_relevant_experience(session, embed, store, user_id, job)
    prompt = await ensure_cover_letter_prompt(session)

    extracted = job.extracted or {}
    responsibilities: list[str] = extracted.get("responsibilities", []) or []
    culture_signals: list[str] = extracted.get("culture_signals", []) or []

    response = await llm.complete(
        prompt.id,
        inputs={
            "experience_items": _format_experience_items(items),
            "job_description": _compose_jd_text(job),
            "responsibilities": "\n".join(f"- {r}" for r in responsibilities),
            "culture_signals": "\n".join(f"- {c}" for c in culture_signals),
            "tone": style.tone,
        },
        response_model=GeneratedDoc,
    )
    if response.parsed is None:
        raise RuntimeError("generate_cover_letter: LLM returned no parsed result")
    return response.parsed.markdown


# ---------------------------------------------------------------------------
# Groundedness judge
# ---------------------------------------------------------------------------


async def check_groundedness(
    session: AsyncSession,
    llm: LLMClient,
    markdown: str,
    experience_items: list[ExperienceItem],
) -> GroundednessResult:
    """LLM-as-judge: map each resume claim to an experience item or flag it.

    Ungrounded claims are surfaced in GroundednessResult.ungrounded so the
    UI can highlight them for the user to review or remove.
    """
    prompt = await ensure_groundedness_prompt(session)

    response = await llm.complete(
        prompt.id,
        inputs={
            "document": markdown,
            "experience_items": _format_experience_items(experience_items),
        },
        response_model=GroundednessResult,
    )
    if response.parsed is None:
        raise RuntimeError("check_groundedness: LLM returned no parsed result")
    result: GroundednessResult = response.parsed
    if result.ungrounded:
        logger.warning(
            "check_groundedness: %d ungrounded claim(s) detected",
            len(result.ungrounded),
        )
    return result


# ---------------------------------------------------------------------------
# Artifact scoring (composition)
# ---------------------------------------------------------------------------


async def score_artifact(
    session: AsyncSession,
    llm: LLMClient,
    markdown: str,
    job: JobPosting,
    groundedness: GroundednessResult,
    match: Match | None,
) -> ArtifactScores:
    """Compose ArtifactScores from deterministic heuristics + LLM groundedness.

    Imports scoring helpers from app.generator.scoring to keep this file
    under 300 lines and allow independent unit testing of the pure functions.
    """
    from app.generator.scoring import compose_artifact_scores

    return compose_artifact_scores(markdown, job, groundedness, match)
