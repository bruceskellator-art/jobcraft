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
    _retrieve_relevant_experience,
    check_groundedness,
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

    # 1. Retrieve the relevant experience subset ONCE — reused for both
    #    generation and groundedness so the judge only sees items the
    #    generator actually had access to.
    retrieved_items = await _retrieve_relevant_experience(
        session, embed, store, user_id, job
    )

    # 2. Generate markdown (pass pre-retrieved items; no second RAG call)
    if kind == "resume":
        markdown, used_items = await generate_resume(
            session, llm, embed, store, user_id, job, style, items=retrieved_items
        )
        from app.generator.service import ensure_resume_prompt

        prompt_version = await ensure_resume_prompt(session)
    else:
        markdown, used_items = await generate_cover_letter(
            session, llm, embed, store, user_id, job, style, items=retrieved_items
        )
        from app.generator.service import ensure_cover_letter_prompt

        prompt_version = await ensure_cover_letter_prompt(session)

    logger.debug("generate_for_job: generated %s (%d chars)", kind, len(markdown))

    # 3. Groundedness check against the SAME subset used for generation
    groundedness = await check_groundedness(session, llm, markdown, used_items)
    if groundedness.ungrounded:
        logger.warning(
            "generate_for_job: %d ungrounded claim(s) in generated %s for job %s",
            len(groundedness.ungrounded),
            kind,
            job.id,
        )

    # 4. Score — thread style.length so clarity uses the right word target
    scores = await score_artifact(
        session, llm, markdown, job, groundedness, match, style.length
    )

    # 5. Optional PDF render (best-effort)
    _ = renderer.render(markdown)

    # 6. Persist artifact — prompt_version already fetched above (no second DB round-trip)
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
    groundedness is measured by running check_groundedness against ALL of
    the user's experience items (makes an LLM call).
    quantified_impact and clarity use deterministic heuristics.
    """
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
