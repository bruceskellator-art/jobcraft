"""Generator service: grounded resume and cover-letter generation.

Prompt ensure_* helpers use the savepoint pattern from matcher/service.py:
speculative insert inside begin_nested(); on IntegrityError roll back only
the savepoint and re-select the already-inserted row.

Resume generation now outputs structured ResumeData JSON (not Markdown).
Cover letter generation still outputs Markdown.
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
from app.generator.types import (
    ArtifactScores,
    GeneratedDoc,
    GroundednessResult,
    ResumeData,
    StyleConfig,
)
from app.llm.client import LLMClient
from app.services.embed_pipeline import _compose_jd_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt constants
# ---------------------------------------------------------------------------

_RESUME_PROMPT_NAME = "generate_resume_v2"
_RESUME_PROMPT_VERSION = 2
_RESUME_PROMPT_MODEL = "claude-sonnet-4-6"
_RESUME_PROMPT_TEMPERATURE = 0.3
_RESUME_PROMPT_TEMPLATE = """\
You are a professional resume writer producing structured JSON resume data.

STRICT RULES:
- Use ONLY facts stated in <experience>. Never invent roles, companies, dates, skills, or metrics.
- Tailor every bullet toward the requirements in <job>.
- Extract name, email, phone, location, linkedin, github from the experience items.
- Return ONLY a valid JSON object — no prose, no markdown fences.
- Tone: {{ tone }}.
- Each bullet must start with a strong action verb and be specific and quantified where possible.

Return an object with this exact schema:
{
  "name": "<full name from experience>",
  "email": "<email from experience>",
  "phone": "<phone or null>",
  "location": "<city, country or null>",
  "linkedin": "<handle e.g. in/username or null>",
  "github": "<handle e.g. github.com/user or null>",
  "website": "<URL or null>",
  "summary": "<2-3 sentence professional summary tailored to the job>",
  "experience": [
    {
      "title": "<job title>",
      "company": "<company name>",
      "location": "<city, state/country or null>",
      "start_date": "<e.g. May 2015>",
      "end_date": "<e.g. Present or November 2015>",
      "bullets": ["<bullet>", ...]
    }
  ],
  "education": [
    {
      "degree": "<degree>",
      "institution": "<school>",
      "location": "<city or null>",
      "year": "<graduation year>",
      "honors": "<honors or null>",
      "minor": "<minor or null>"
    }
  ],
  "skills": [
    { "category": "<category>", "skills": ["<skill>", ...] }
  ],
  "projects": [
    {
      "name": "<project>",
      "role": "<role or null>",
      "organization": "<org or null>",
      "start_date": "<date or null>",
      "end_date": "<date or null>",
      "bullets": ["<bullet>", ...]
    }
  ]
}

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
    """Return (or create) the active generate_resume_v2 PromptVersion."""
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
# Experience loading
# ---------------------------------------------------------------------------


async def _load_all_experience(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[ExperienceItem]:
    """Load all experience items for a user from the database."""
    result = await session.execute(
        select(ExperienceItem).where(ExperienceItem.user_id == user_id)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_experience_items(items: list[ExperienceItem]) -> str:
    return "\n\n".join(
        f"{idx + 1}. [{item.kind}] {item.title or '(untitled)'} "
        f"(id={item.id})\n{item.content}"
        for idx, item in enumerate(items)
    )


def _resume_data_to_text(data: ResumeData) -> str:
    """Flatten ResumeData to plain text for groundedness checking and scoring."""
    lines: list[str] = []
    if data.summary:
        lines.append(data.summary)
    for exp in data.experience:
        lines.extend(exp.bullets)
    for proj in data.projects:
        lines.extend(proj.bullets)
    return "\n".join(f"- {line}" for line in lines)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


async def generate_resume(
    session: AsyncSession,
    llm: LLMClient,
    user_id: uuid.UUID,
    job: JobPosting,
    style: StyleConfig,
) -> tuple[ResumeData, list[ExperienceItem]]:
    """Generate a grounded structured resume tailored to a job posting.

    Returns (ResumeData, experience_items_used). The caller can reuse the
    returned items list for groundedness checking.
    """
    items = await _load_all_experience(session, user_id)
    prompt = await ensure_resume_prompt(session)

    response = await llm.complete(
        prompt.id,
        inputs={
            "experience_items": _format_experience_items(items),
            "job_description": _compose_jd_text(job),
            "tone": style.tone,
            "emphasis": ", ".join(style.emphasis) if style.emphasis else "",
        },
        response_model=ResumeData,
    )
    if response.parsed is None:
        raise RuntimeError("generate_resume: LLM returned no parsed result")
    return response.parsed, items


async def generate_cover_letter(
    session: AsyncSession,
    llm: LLMClient,
    user_id: uuid.UUID,
    job: JobPosting,
    style: StyleConfig,
) -> tuple[str, list[ExperienceItem]]:
    """Generate a grounded Markdown cover letter tailored to a job posting.

    Returns (markdown, experience_items_used).
    """
    items = await _load_all_experience(session, user_id)
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
    return response.parsed.markdown, items


# ---------------------------------------------------------------------------
# Groundedness judge
# ---------------------------------------------------------------------------


async def check_groundedness(
    session: AsyncSession,
    llm: LLMClient,
    document_text: str,
    experience_items: list[ExperienceItem],
) -> GroundednessResult:
    """LLM-as-judge: map each resume claim to an experience item or flag it."""
    prompt = await ensure_groundedness_prompt(session)

    response = await llm.complete(
        prompt.id,
        inputs={
            "document": document_text,
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
    document_text: str,
    job: JobPosting,
    groundedness: GroundednessResult,
    match: Match | None,
    length: str = "one_page",
) -> ArtifactScores:
    """Compose ArtifactScores from deterministic heuristics + LLM groundedness."""
    from app.generator.scoring import compose_artifact_scores

    return compose_artifact_scores(document_text, job, groundedness, match, length)
