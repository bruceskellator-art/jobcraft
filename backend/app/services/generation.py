"""Generation orchestration service.

Ties together RAG retrieval, LLM generation, groundedness checking,
scoring, and artifact persistence into two public entry points:

  - generate_for_job: full pipeline for resume or cover letter
  - score_baseline: score an uploaded résumé without a job context
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.artifact import Artifact
from app.db.models.experience_item import ExperienceItem
from app.db.models.job_posting import JobPosting
from app.db.models.match import Match
from app.embeddings.base import EmbeddingClient
from app.generator.pdf import NullPdfRenderer, PdfRenderer
from app.generator.scoring import score_clarity, score_quantified_impact
from app.generator.service import (
    check_groundedness,
    ensure_cover_letter_prompt,
    ensure_resume_prompt,
    generate_cover_letter,
    generate_resume,
    score_artifact,
)
from app.generator.types import ArtifactScores, StyleConfig
from app.llm.client import LLMClient
from app.repositories.artifact import ArtifactRepository
from app.vectorstore.base import VectorStore

logger = logging.getLogger(__name__)


async def generate_for_job(
    session: AsyncSession,
    llm: LLMClient,
    embed: EmbeddingClient,
    store: VectorStore,
    user_id: uuid.UUID,
    job: JobPosting,
    kind: str,
    style: StyleConfig,
    *,
    pdf: PdfRenderer | None = None,
    match: Match | None = None,
) -> Artifact:
    """Full generation pipeline: generate → ground → score → persist.

    Parameters
    ----------
    kind:
        'resume' or 'cover_letter'
    pdf:
        Optional renderer. Defaults to NullPdfRenderer (no PDF output).
        artifact.content always stores Markdown regardless.
    match:
        Pre-computed Match for fit scoring. If None, fit score is 0.0.

    The caller is responsible for committing the session after this returns.
    """
    if kind not in ("resume", "cover_letter"):
        raise ValueError(f"kind must be 'resume' or 'cover_letter', got {kind!r}")

    renderer = pdf if pdf is not None else NullPdfRenderer()

    # 1. Generate markdown
    if kind == "resume":
        markdown = await generate_resume(session, llm, embed, store, user_id, job, style)
    else:
        markdown = await generate_cover_letter(session, llm, embed, store, user_id, job, style)

    logger.debug("generate_for_job: generated %s (%d chars)", kind, len(markdown))

    # 2. Groundedness check — surface ungrounded claims, do not drop them
    result = await session.execute(
        select(ExperienceItem).where(ExperienceItem.user_id == user_id)
    )
    experience_items = list(result.scalars().all())

    groundedness = await check_groundedness(session, llm, markdown, experience_items)
    if groundedness.ungrounded:
        logger.warning(
            "generate_for_job: %d ungrounded claim(s) in generated %s for job %s",
            len(groundedness.ungrounded),
            kind,
            job.id,
        )

    # 3. Score
    scores = await score_artifact(session, llm, markdown, job, groundedness, match)

    # 4. Optional PDF render (best-effort)
    _ = renderer.render(markdown)

    # 5. Persist artifact
    prompt_version = (
        await ensure_resume_prompt(session)
        if kind == "resume"
        else await ensure_cover_letter_prompt(session)
    )

    repo = ArtifactRepository(session)
    artifact = await repo.create(
        user_id=user_id,
        job_id=job.id,
        kind=kind,
        format="markdown",
        content=markdown,
        is_baseline=False,
        scores=scores.model_dump(),
        prompt_version_id=prompt_version.id,
        generation_run_id=uuid.uuid4(),
    )
    logger.info(
        "generate_for_job: persisted artifact %s (kind=%s, job=%s)", artifact.id, kind, job.id
    )
    return artifact


async def score_baseline(
    session: AsyncSession,
    llm: LLMClient,
    user_id: uuid.UUID,
    baseline_markdown: str,
) -> ArtifactScores:
    """Score an uploaded baseline résumé with no job context.

    fit and ats_keywords are 0.0 (no job to compare against).
    groundedness, quantified_impact, and clarity use deterministic heuristics
    only — no LLM call needed.
    """
    return ArtifactScores(
        fit=0.0,
        groundedness=0.0,
        ats_keywords=0.0,
        quantified_impact=score_quantified_impact(baseline_markdown),
        clarity=score_clarity(baseline_markdown),
    )
