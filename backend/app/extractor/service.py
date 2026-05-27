from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.prompt_version import PromptVersion
from app.extractor.types import ExtractedJob
from app.llm.client import LLMClient
from app.llm.errors import LLMError

logger = logging.getLogger(__name__)

_PROMPT_NAME = "extract_job"
_PROMPT_VERSION = 1
_PROMPT_MODEL = "claude-sonnet-4-6"
_PROMPT_TEMPERATURE = 0.0
_PROMPT_TEMPLATE = """\
You are an expert job posting parser.

Extract structured information from the job posting below and return it as a JSON
object matching exactly this schema:

{
  "company": "<company name>",
  "title": "<job title>",
  "seniority": "<junior|mid|senior|staff|principal or null>",
  "location": "<city, state/country or null>",
  "remote_policy": "<remote|hybrid|onsite or null>",
  "salary_min_usd": <integer or null>,
  "salary_max_usd": <integer or null>,
  "required_skills": ["<must-have skill>"],
  "preferred_skills": ["<nice-to-have skill>"],
  "responsibilities": ["<responsibility>"],
  "qualifications": ["<qualification>"],
  "culture_signals": ["<culture signal, e.g. values move-fast>"],
  "summary": "<2-3 sentence summary for UI display>"
}

Rules:
- Return ONLY valid JSON. No prose, no markdown fences.
- If a field is unknown or not mentioned, use null for scalar fields or [] for arrays.
- Salary values must be integers in USD per year; use null if not specified or not USD.
- seniority must be one of: junior, mid, senior, staff, principal — or null.
- remote_policy must be one of: remote, hybrid, onsite — or null.

Job posting:
<job_posting>
{{ raw_content }}
</job_posting>
"""


async def ensure_extract_prompt(session: AsyncSession) -> PromptVersion:
    """Return the active extract_job PromptVersion, creating it if absent.

    Idempotent: concurrent callers are safe because an IntegrityError on the
    unique index causes a rollback and re-select of the existing row.
    """
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


async def extract_job(
    session: AsyncSession,
    llm: LLMClient,
    raw_content: str,
) -> ExtractedJob | None:
    """Extract a structured ExtractedJob from raw job posting text.

    Calls the LLM once; retries once on LLMError (parse failure). If both
    attempts fail, logs a warning and returns None — the failed calls are
    already recorded in llm_calls.error by LLMClient.

    Note: The spec mentions a "fix this JSON" follow-up prompt as a second
    retry strategy. For now, retry-once-then-give-up satisfies the contract.
    A dedicated fix-prompt is a noted future refinement.

    Args:
        session: Active async database session.
        llm: LLMClient wired to an adapter.
        raw_content: Raw text scraped from the job posting page.

    Returns:
        Parsed ExtractedJob on success, None if both LLM attempts fail.

    Raises:
        ValueError: If raw_content is empty or whitespace-only.
    """
    if not raw_content or not raw_content.strip():
        raise ValueError("raw_content must not be empty.")

    prompt = await ensure_extract_prompt(session)

    for attempt in range(2):
        try:
            response = await llm.complete(
                prompt.id,
                inputs={"raw_content": raw_content},
                response_model=ExtractedJob,
            )
            return response.parsed
        except LLMError:
            if attempt == 0:
                logger.warning(
                    "extract_job: LLM parse failed on attempt 1, retrying once."
                )
            else:
                logger.warning(
                    "extract_job: LLM parse failed on both attempts, giving up."
                )

    return None
