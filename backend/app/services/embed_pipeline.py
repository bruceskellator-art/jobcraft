"""Embedding pipeline helpers for indexing user experience and job postings.

JD text composition for index_job:
  - If job.extracted is a non-None dict, compose:
      "{job.title}\n{extracted['summary']}\n{', '.join(extracted['required_skills'])}"
    using summary and required_skills from the extracted dict (empty string / empty
    list if those keys are absent).
  - Otherwise fall back to: "{job.title}\n{job.raw_content}"

Using the structured extraction when available produces a denser, higher-signal
embedding. Falling back to raw content means unextracted jobs are still indexed.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.experience_item import ExperienceItem
from app.db.models.job_posting import JobPosting
from app.embeddings.base import EmbeddingClient
from app.repositories.experience import ExperienceRepository
from app.vectorstore.base import VectorPoint, VectorStore

logger = logging.getLogger(__name__)

COLLECTION_USER_EXPERIENCE = "user_experience"
COLLECTION_JOB_POSTINGS = "job_postings"


def _compose_jd_text(job: JobPosting) -> str:
    if job.extracted is not None:
        summary = job.extracted.get("summary", "") or ""
        required_skills: list[str] = job.extracted.get("required_skills", []) or []
        skills_str = ", ".join(required_skills)
        return f"{job.title}\n{summary}\n{skills_str}"
    return f"{job.title}\n{job.raw_content}"


async def index_user_experience(
    session: AsyncSession,
    embed: EmbeddingClient,
    store: VectorStore,
    user_id: uuid.UUID,
) -> None:
    """Embed each experience item for user_id and upsert into the vector store.

    Each point carries payload: {user_id, experience_id, kind}.
    """
    repo = ExperienceRepository(session)
    items: list[ExperienceItem] = await repo.list_by_user(user_id)
    if not items:
        logger.debug("No experience items for user %s — nothing to index", user_id)
        return

    await store.ensure_collection(COLLECTION_USER_EXPERIENCE, embed.dim)

    texts = [item.content for item in items]
    vectors = await embed.embed(texts)

    points = [
        VectorPoint(
            id=str(item.id),
            vector=vector,
            payload={
                "user_id": str(user_id),
                "experience_id": str(item.id),
                "kind": item.kind,
            },
        )
        for item, vector in zip(items, vectors, strict=True)
    ]
    await store.upsert(COLLECTION_USER_EXPERIENCE, points)
    logger.debug("Indexed %d experience items for user %s", len(points), user_id)


async def index_job(
    embed: EmbeddingClient,
    store: VectorStore,
    job: JobPosting,
) -> None:
    """Embed a job posting and upsert it into the vector store.

    Text composition prefers the structured extraction when available.
    Point payload: {job_id, company}.
    """
    await store.ensure_collection(COLLECTION_JOB_POSTINGS, embed.dim)

    text = _compose_jd_text(job)
    vectors = await embed.embed([text])

    point = VectorPoint(
        id=str(job.id),
        vector=vectors[0],
        payload={"job_id": str(job.id), "company": job.company},
    )
    await store.upsert(COLLECTION_JOB_POSTINGS, [point])
    logger.debug("Indexed job %s (%s)", job.id, job.title)


async def user_corpus_vectors(
    session: AsyncSession,
    embed: EmbeddingClient,
    user_id: uuid.UUID,
) -> list[list[float]]:
    """Return embedded vectors for all experience items belonging to user_id.

    Side-effect-free: does not write to the vector store. Used by the
    prefilter stage to compute a corpus centroid without indexing.
    """
    repo = ExperienceRepository(session)
    items: list[ExperienceItem] = await repo.list_by_user(user_id)
    if not items:
        return []

    texts = [item.content for item in items]
    return await embed.embed(texts)
