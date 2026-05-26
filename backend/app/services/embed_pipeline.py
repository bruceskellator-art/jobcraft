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


async def get_user_vectors(store: VectorStore, user_id: uuid.UUID) -> list[list[float]]:
    """Fetch already-indexed experience vectors for user_id from the vector store.

    Returns the raw float vectors stored in COLLECTION_USER_EXPERIENCE for the
    given user. Returns an empty list when the user has not yet been indexed.

    This is the correct prefilter path: the corpus is embedded ONCE via
    ``index_user_experience``; subsequent prefilter calls read stored vectors
    rather than re-embedding from the database.

    Implementation strategy
    -----------------------
    The VectorStore Protocol's ``search`` method performs ANN (approximate
    nearest-neighbour) lookup and requires a query vector of the correct
    dimension.  Since we need *all* vectors for a user (not a ranked subset),
    we bypass ``search`` entirely and read from the store's internal state:

    - InMemoryVectorStore exposes ``_collections`` (dict of VectorPoint).
    - QdrantVectorStore exposes ``_client`` with a ``scroll`` API that returns
      points with vectors when ``with_vectors=True``.
    - Any other store that exposes ``_collections`` in the same shape is also
      supported automatically.
    """
    # InMemoryVectorStore (and any store with the same _collections shape)
    internal = getattr(store, "_collections", None)
    if internal is not None:
        collection: dict = internal.get(COLLECTION_USER_EXPERIENCE, {})
        uid_str = str(user_id)
        return [
            vp.vector
            for vp in collection.values()
            if vp.payload.get("user_id") == uid_str
        ]

    # QdrantVectorStore: use scroll to retrieve points with vectors.
    qdrant_client = getattr(store, "_client", None)
    if qdrant_client is not None:
        try:
            from qdrant_client.http import models as qmodels

            scroll_result, _ = await qdrant_client.scroll(
                collection_name=COLLECTION_USER_EXPERIENCE,
                scroll_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="user_id",
                            match=qmodels.MatchValue(value=str(user_id)),
                        )
                    ]
                ),
                with_vectors=True,
                limit=1000,
            )
            return [
                list(p.vector) if not isinstance(p.vector, list) else p.vector
                for p in scroll_result
                if p.vector is not None
            ]
        except Exception:
            logger.warning(
                "get_user_vectors: failed to scroll Qdrant for user %s", user_id
            )
            return []

    # Unknown store type — cannot retrieve raw vectors.
    logger.warning(
        "get_user_vectors: unsupported store type %s, returning empty corpus",
        type(store).__name__,
    )
    return []
