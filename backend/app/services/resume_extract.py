from __future__ import annotations

import io
import logging
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.experience_item import ExperienceItem
from app.db.models.prompt_version import PromptVersion
from app.llm.client import LLMClient
from app.repositories.experience import ExperienceRepository
from app.schemas.experience import ExperienceItemCreate
from app.schemas.resume_import import ResumeExtractionResult

logger = logging.getLogger(__name__)

_PROMPT_NAME = "extract_resume"
_PROMPT_VERSION = 1
_PROMPT_MODEL = "claude-sonnet-4-6"
_PROMPT_TEMPERATURE = 0.0
_PROMPT_TEMPLATE = """\
You are an expert resume parser.

Extract ALL experiences from the resume text below and return them as a JSON object
matching exactly this schema:

{
  "items": [
    {
      "kind": "<work|project|education|skill|achievement>",
      "title": "<role or credential title>",
      "organization": "<company, school, or issuer>",
      "content": "<concise summary of responsibilities, achievements, or description>",
      "start_date": "<YYYY-MM or null>",
      "end_date": "<YYYY-MM or null>",
      "tags": ["<relevant skill or keyword>"]
    }
  ]
}

Rules:
- Use kind "work" for employment, "project" for personal/open-source projects,
  "education" for degrees/certifications, "skill" for standalone skills,
  "achievement" for awards or notable accomplishments.
- Return ONLY valid JSON. No prose, no markdown fences.
- If a field is unknown, use null for dates or an empty string for text fields.

Resume text:
<resume>
{{ resume_text }}
</resume>
"""


def extract_text_from_pdf(data: bytes) -> str:
    """Extract plain text from PDF bytes using pypdf.

    Raises ValueError if the PDF is unreadable or yields no text content.
    """
    try:
        from pypdf import PdfReader  # local import keeps startup fast
    except ImportError as exc:
        raise ImportError("pypdf is required: pip install pypdf") from exc

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:
        raise ValueError("Could not parse the uploaded file as a PDF.") from None

    pages_text = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages_text).strip()

    if not text:
        raise ValueError("PDF contains no extractable text (may be scanned/image-only).")

    return text


async def ensure_extraction_prompt(session: AsyncSession) -> PromptVersion:
    """Return the active extract_resume PromptVersion, creating it if absent.

    Idempotent: calling twice with the same session will not insert a duplicate
    because the one_active_per_name partial unique index prevents it.
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
        # Another concurrent request already inserted the row; re-select it.
        result = await session.execute(
            select(PromptVersion).where(
                PromptVersion.name == _PROMPT_NAME,
                PromptVersion.is_active == True,  # noqa: E712
            )
        )
        prompt = result.scalar_one()
    return prompt


def _parse_date(value: str | None) -> date | None:
    """Parse a YYYY-MM or YYYY-MM-DD string into a date, returning None on failure."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


async def import_resume_from_text(
    session: AsyncSession,
    llm: LLMClient,
    user_id: uuid.UUID,
    resume_text: str,
) -> list[ExperienceItem]:
    """Core business logic: extract structured items from resume text and persist them.

    Args:
        session: Active async database session.
        llm: LLMClient wired to either AnthropicAdapter (prod) or MockAdapter (tests).
        user_id: Owner of the created ExperienceItems.
        resume_text: Plain text extracted from the uploaded PDF.

    Returns:
        List of newly created ExperienceItem ORM instances.

    Raises:
        ValueError: If resume_text is empty.
    """
    if not resume_text or not resume_text.strip():
        raise ValueError("resume_text must not be empty.")

    prompt = await ensure_extraction_prompt(session)
    response = await llm.complete(
        prompt.id,
        inputs={"resume_text": resume_text},
        response_model=ResumeExtractionResult,
    )

    extraction: ResumeExtractionResult = response.parsed  # type: ignore[assignment]
    repo = ExperienceRepository(session)
    created: list[ExperienceItem] = []

    for item in extraction.items:
        # Use explicit empty list rather than None so the ORM stores [] not the
        # server-default `{}` (a JSON object), which would fail Pydantic validation
        # on read-back in SQLite.
        tags: list[str] = list(item.tags) if item.tags else []
        create_schema = ExperienceItemCreate(
            kind=item.kind,
            title=item.title or None,
            organization=item.organization or None,
            content=item.content or item.title,
            start_date=_parse_date(item.start_date),
            end_date=_parse_date(item.end_date),
            tags=tags,
        )
        experience = await repo.create(user_id, create_schema)
        created.append(experience)

    return created
