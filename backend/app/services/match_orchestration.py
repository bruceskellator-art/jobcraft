"""High-level orchestration for the two-stage job-match pipeline.

This module coordinates the embedding pipeline (user indexing, job indexing)
with the matcher service (prefilter + LLM judge) and exposes three entry points:

- ``ensure_user_indexed``  — idempotent: index user experience into vector store.
- ``match_job``            — run full match for a single job, return a Match row.
- ``match_all_jobs``       — bulk-match recent jobs; return {matched, failed, total}.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.job_posting import JobPosting
from app.db.models.match import Match
from app.embeddings.base import EmbeddingClient
from app.llm.client import LLMClient
from app.matcher.service import compute_match
from app.services.embed_pipeline import index_job, index_user_experience
from app.vectorstore.base import VectorStore

logger = logging.getLogger(__name__)

_DEFAULT_JOB_LIMIT = 50


async def ensure_user_indexed(
    session: AsyncSession,
    embed: EmbeddingClient,
    store: VectorStore,
    user_id: uuid.UUID,
) -> None:
    """Embed the user's experience items into the vector store (idempotent).

    Safe to call multiple times — ``index_user_experience`` upserts by point id
    so re-indexing an unchanged corpus is a no-op at the store level.
    """
    await index_user_experience(session, embed, store, user_id)


async def match_job(
    session: AsyncSession,
    llm: LLMClient,
    embed: EmbeddingClient,
    store: VectorStore,
    user_id: uuid.UUID,
    job: JobPosting,
) -> Match:
    """Run the full two-stage match for *job* against *user_id* and persist it.

    Steps:
    1. Ensure user corpus is indexed (idempotent).
    2. Index the job posting (idempotent upsert).
    3. Run ``compute_match`` (prefilter → optional LLM judge → persist).

    Returns the persisted Match row. Does NOT commit — the caller is responsible
    for committing the session transaction.
    """
    await ensure_user_indexed(session, embed, store, user_id)
    await index_job(embed, store, job)
    return await compute_match(session, llm, embed, store, user_id, job)


async def match_all_jobs(
    session: AsyncSession,
    llm: LLMClient,
    embed: EmbeddingClient,
    store: VectorStore,
    user_id: uuid.UUID,
    *,
    limit: int = _DEFAULT_JOB_LIMIT,
    only_unscored: bool = True,
) -> dict[str, int]:
    """Match up to *limit* most-recent job postings for *user_id*.

    When ``only_unscored`` (the default), jobs that already have a Match for this
    user are excluded via a LEFT JOIN ... IS NULL, so re-runs only score new jobs.

    Per-job failures are logged and isolated with ``begin_nested()`` — a single
    bad job does not abort the run. Returns ``{"matched", "failed", "total"}``
    where ``total`` is the number of jobs attempted.

    Kept SEQUENTIAL on purpose: the single AsyncSession is not safe for concurrent
    tasks. Backgrounding / per-job concurrency (separate sessions) is a future step.

    Does NOT commit the session — the caller commits once after the run.
    """
    stmt = select(JobPosting)
    if only_unscored:
        scored_subq = select(Match.job_id).where(Match.user_id == user_id)
        stmt = stmt.where(JobPosting.id.notin_(scored_subq))
    stmt = stmt.order_by(JobPosting.scraped_at.desc()).limit(limit)

    result = await session.execute(stmt)
    jobs = list(result.scalars().all())

    if not jobs:
        logger.info("match_all_jobs: no jobs to match for user %s", user_id)
        return {"matched": 0, "failed": 0, "total": 0}

    # Index the user once before the per-job loop.
    await ensure_user_indexed(session, embed, store, user_id)

    matched = 0
    failed = 0
    for job in jobs:
        try:
            async with session.begin_nested():
                await index_job(embed, store, job)
                await compute_match(session, llm, embed, store, user_id, job)
            matched += 1
        except Exception:
            failed += 1
            logger.exception(
                "match_all_jobs: failed to match job %s for user %s — skipping",
                job.id,
                user_id,
            )

    logger.info(
        "match_all_jobs: matched %d failed %d of %d jobs for user %s",
        matched,
        failed,
        len(jobs),
        user_id,
    )
    return {"matched": matched, "failed": failed, "total": len(jobs)}
