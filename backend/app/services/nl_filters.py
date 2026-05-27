from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.prompt_version import PromptVersion
from app.llm.client import LLMClient
from app.scrapers.types import JobFilters

logger = logging.getLogger(__name__)

_PROMPT_NAME = "parse_job_filters"
_PROMPT_VERSION = 1
_PROMPT_MODEL = "claude-haiku-4-5"
_PROMPT_TEMPERATURE = 0.0
_PROMPT_TEMPLATE = """\
Convert the natural-language job search query below into a JSON object \
that matches this schema exactly:

{
  "keywords": ["<keyword>", ...],
  "companies": ["<company>", ...] or null,
  "locations": ["<location>", ...] or null,
  "remote_only": true or false,
  "seniority": ["junior"|"mid"|"senior"|"staff", ...] or null,
  "posted_within_days": <integer, default 30>
}

Rules:
- Return ONLY valid JSON. No prose, no markdown fences.
- Use null (not an empty array) when a field is not mentioned.
- posted_within_days defaults to 30 unless the query mentions a timeframe.
- seniority values must be one of: junior, mid, senior, staff.

Query:
<query>
{{ query }}
</query>
"""


async def _ensure_prompt(session: AsyncSession) -> PromptVersion:
    """Return the active parse_job_filters PromptVersion, creating it if absent."""
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


async def parse_filters(session: AsyncSession, llm: LLMClient, text: str) -> JobFilters:
    """Convert a natural-language query into a typed JobFilters object via LLM."""
    prompt = await _ensure_prompt(session)
    response = await llm.complete(
        prompt.id,
        inputs={"query": text},
        response_model=JobFilters,
    )
    filters: JobFilters = response.parsed  # type: ignore[assignment]
    return filters
