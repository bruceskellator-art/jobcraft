"""Generation orchestration service."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.artifact import Artifact
from app.db.models.experience_item import ExperienceItem
from app.db.models.job_posting import JobPosting
from app.db.models.match import Match
from app.generator.scoring import score_clarity, score_quantified_impact
from app.generator.service import (
    _resume_data_to_text,
    check_groundedness,
    generate_cover_letter,
    generate_resume,
    score_artifact,
)
from app.generator.types import ArtifactScores, StyleConfig
from app.llm.client import LLMClient
from app.repositories.artifact import ArtifactRepository
from app.resume_templates.registry import get_template

logger = logging.getLogger(__name__)


async def generate_for_job(
    session: AsyncSession,
    llm: LLMClient,
    user_id: uuid.UUID,
    job: JobPosting,
    kind: str,
    style: StyleConfig,
    *,
    template_id: str = "standard",
    match: Match | None = None,
) -> Artifact:
    """Full generation pipeline: generate → ground → score → persist.

    For resumes: LLM → ResumeData JSON → store JSON + template_id.
    For cover letters: LLM → Markdown → store markdown.
    The caller is responsible for committing the session after this returns.
    """
    if kind not in ("resume", "cover_letter"):
        raise ValueError(f"kind must be 'resume' or 'cover_letter', got {kind!r}")

    if kind == "resume":
        resume_data, used_items = await generate_resume(session, llm, user_id, job, style)
        from app.generator.service import ensure_resume_prompt
        prompt_version = await ensure_resume_prompt(session)

        document_text = _resume_data_to_text(resume_data)
        groundedness = await check_groundedness(session, llm, document_text, used_items)

        scores = await score_artifact(
            session, llm, document_text, job, groundedness, match, style.length
        )

        if get_template(template_id) is None:
            logger.warning("generate_for_job: unknown template %r, using standard", template_id)
            template_id = "standard"

        content = resume_data.model_dump_json()
        artifact_format = "json"
        stored_template_id: str | None = template_id

    else:
        markdown, used_items = await generate_cover_letter(session, llm, user_id, job, style)
        from app.generator.service import ensure_cover_letter_prompt
        prompt_version = await ensure_cover_letter_prompt(session)

        groundedness = await check_groundedness(session, llm, markdown, used_items)

        scores = await score_artifact(
            session, llm, markdown, job, groundedness, match, style.length
        )

        content = markdown
        artifact_format = "markdown"
        stored_template_id = None

    if groundedness.ungrounded:
        logger.warning(
            "generate_for_job: %d ungrounded claim(s) in %s for job %s",
            len(groundedness.ungrounded), kind, job.id,
        )

    repo = ArtifactRepository(session)
    artifact = await repo.create(
        user_id=user_id,
        job_id=job.id,
        kind=kind,
        format=artifact_format,
        content=content,
        is_baseline=False,
        scores=scores.model_dump(),
        prompt_version_id=prompt_version.id,
        generation_run_id=uuid.uuid4(),
        template_id=stored_template_id,
    )
    logger.info(
        "generate_for_job: persisted artifact %s (kind=%s, template=%s, job=%s)",
        artifact.id, kind, stored_template_id, job.id,
    )
    return artifact


async def score_baseline(
    session: AsyncSession,
    llm: LLMClient,
    user_id: uuid.UUID,
    baseline_markdown: str,
) -> ArtifactScores:
    """Score an uploaded baseline résumé with no job context."""
    result = await session.execute(
        select(ExperienceItem).where(ExperienceItem.user_id == user_id)
    )
    experience_items = list(result.scalars().all())

    groundedness = await check_groundedness(
        session, llm, baseline_markdown, experience_items
    )

    return ArtifactScores(
        fit=0.0,
        groundedness=groundedness.grounded_ratio,
        ats_keywords=0.0,
        quantified_impact=score_quantified_impact(baseline_markdown),
        clarity=score_clarity(baseline_markdown),
    )
