"""Email status classifier — maps an email to an EmailStatusInference.

Every classification is a prompt-versioned LLMClient call so it is logged to
llm_calls and can be evaluated/tuned with its own eval suite
(status_classification_v1 per §4.9).
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.email_sync.provider import RawEmail
from app.llm.client import LLMClient

logger = logging.getLogger(__name__)

_PROMPT_NAME = "classify_email_status"
_PROMPT_VERSION = 1
_PROMPT_MODEL = "claude-haiku-4-5"
_PROMPT_TEMPERATURE = 0.0
_PROMPT_TEMPLATE = """\
You are an expert job-search assistant. Classify the recruitment email below.

Return ONLY a JSON object matching exactly this schema — no prose, no fences:
{
  "classification": "<acknowledged|assessment|phone_screen|technical|onsite
                    |offer|rejected|ghosted_followup|other>",
  "confidence": <float 0.0..1.0>,
  "suggested_status": "<the application status this maps to>",
  "evidence": "<one short quoted line from the email that justifies the classification>",
  "requires_human": <true if offer or rejected, false otherwise>
}

suggested_status must be one of: interested, queued, submitted, phone_screen,
technical, onsite, offer, rejected, withdrawn.

<email>
From: {{ from_address }}
Subject: {{ subject }}
---
{{ body_excerpt }}
</email>
"""

_BODY_EXCERPT_CHARS = 2000  # max characters of body to send to LLM


class EmailStatusInference(BaseModel):
    """Structured output from the email status classifier (spec §4.9)."""

    classification: Literal[
        "acknowledged",
        "assessment",
        "phone_screen",
        "technical",
        "onsite",
        "offer",
        "rejected",
        "ghosted_followup",
        "other",
    ]
    confidence: float  # 0..1
    suggested_status: str  # maps to applications.status
    evidence: str  # one quoted line that justifies the classification (for UI)
    requires_human: bool  # true for offer/rejected → always confirm


async def ensure_classify_prompt(session: AsyncSession) -> PromptVersion:  # type: ignore[name-defined]  # noqa: F821
    """Return or create the classify_email_status PromptVersion.

    Idempotent: safe under concurrent callers — the speculative INSERT is scoped
    to a savepoint so an IntegrityError rolls back only that insert and leaves
    the outer transaction intact. (Same pattern as ensure_match_prompt.)
    """
    from app.db.models.prompt_version import PromptVersion

    result = await session.execute(
        select(PromptVersion).where(
            PromptVersion.name == _PROMPT_NAME,
            PromptVersion.is_active == True,  # noqa: E712
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    prompt = PromptVersion(
        name=_PROMPT_NAME,
        version=_PROMPT_VERSION,
        template=_PROMPT_TEMPLATE,
        model=_PROMPT_MODEL,
        temperature=_PROMPT_TEMPERATURE,
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
                PromptVersion.name == _PROMPT_NAME,
                PromptVersion.is_active == True,  # noqa: E712
            )
        )
        prompt = result.scalar_one()
    return prompt


async def classify_email(
    session: AsyncSession,
    llm: LLMClient,
    raw: RawEmail,
) -> EmailStatusInference:
    """Classify the status signal in *raw* using the LLM.

    The email body is wrapped in <email> delimiters and truncated to
    _BODY_EXCERPT_CHARS to keep token counts bounded.

    Returns:
        An EmailStatusInference with classification, confidence,
        suggested_status, evidence, and requires_human.

    Raises:
        LLMError: if the adapter or JSON parsing fails.
    """
    prompt = await ensure_classify_prompt(session)

    # Truncate body to avoid bloating token budget
    body_excerpt = (raw.body or "")[:_BODY_EXCERPT_CHARS]

    response = await llm.complete(
        prompt.id,
        inputs={
            "from_address": raw.from_address,
            "subject": raw.subject or "(no subject)",
            "body_excerpt": body_excerpt,
        },
        response_model=EmailStatusInference,
    )
    # response.parsed is guaranteed non-None when response_model is provided
    # and no LLMError was raised.
    return response.parsed  # type: ignore[return-value]
