"""Match API endpoints.

Routes
------
GET  /api/jobs/{job_id}/match   Compute (or return cached) match for current user.
POST /api/match/run             Bulk-match the N most-recent jobs for current user.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.user import User
from app.deps import (
    get_current_user,
    get_embedding_client,
    get_llm_client,
    get_vector_store,
)
from app.embeddings.base import EmbeddingClient
from app.llm.client import LLMClient
from app.repositories.job import JobRepository
from app.schemas.match import MatchRead
from app.services.match_orchestration import match_all_jobs, match_job
from app.vectorstore.base import VectorStore

router = APIRouter(tags=["match"])


class RunMatchRequest(BaseModel):
    """Request body for POST /api/match/run."""

    limit: int = 50


class RunMatchResponse(BaseModel):
    """Response body for POST /api/match/run."""

    matched: int


@router.get("/api/jobs/{job_id}/match", response_model=MatchRead)
async def get_job_match(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
    embed: EmbeddingClient = Depends(get_embedding_client),  # noqa: B008
    store: VectorStore = Depends(get_vector_store),  # noqa: B008
) -> MatchRead:
    """Compute (or return the cached) match score for a single job.

    Returns 404 if the job posting does not exist.
    Commits the session after a successful match computation.
    """
    repo = JobRepository(session)
    job = await repo.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found",
        )

    match = await match_job(session, llm, embed, store, current_user.id, job)
    await session.commit()
    return MatchRead.model_validate(match)


@router.post("/api/match/run", response_model=RunMatchResponse)
async def run_match(
    body: RunMatchRequest = RunMatchRequest(),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
    embed: EmbeddingClient = Depends(get_embedding_client),  # noqa: B008
    store: VectorStore = Depends(get_vector_store),  # noqa: B008
) -> RunMatchResponse:
    """Bulk-match the *limit* most-recent job postings for the current user.

    Per-job failures are isolated — a single bad job does not abort the run.
    Commits the session after all jobs have been processed.
    """
    count = await match_all_jobs(
        session, llm, embed, store, current_user.id, limit=body.limit
    )
    await session.commit()
    return RunMatchResponse(matched=count)
