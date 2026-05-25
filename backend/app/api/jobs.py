from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.deps import get_llm_client, get_source_factory
from app.llm.client import LLMClient
from app.repositories.job import JobRepository
from app.schemas.job import JobPostingRead, ScrapeRequest, ScrapeResponse, ScrapeRunLogView
from app.scrapers.base import JobSource
from app.services.scrape import run_scrape

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _get_repo(session: AsyncSession = Depends(get_session)) -> JobRepository:  # noqa: B008
    return JobRepository(session)


@router.get("", response_model=list[JobPostingRead])
async def list_jobs(
    source: str | None = None,
    q: str | None = None,
    repo: JobRepository = Depends(_get_repo),  # noqa: B008
) -> list[JobPostingRead]:
    """List job postings with optional source and full-text query filters."""
    items = await repo.list(source=source, query=q)
    return items  # type: ignore[return-value]


@router.get("/{job_id}", response_model=JobPostingRead)
async def get_job(
    job_id: uuid.UUID,
    repo: JobRepository = Depends(_get_repo),  # noqa: B008
) -> JobPostingRead:
    """Retrieve a single job posting by ID. Returns 404 if not found."""
    posting = await repo.get(job_id)
    if posting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found",
        )
    return posting  # type: ignore[return-value]


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_jobs(
    body: ScrapeRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    source_factory: Callable[[list[str], list[str]], list[JobSource]] = Depends(get_source_factory),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> ScrapeResponse:
    """Trigger a scrape across Greenhouse and/or Lever sources.

    Builds JobSource instances via the injected source_factory so tests
    can override it to inject fake sources with no network calls.
    Each owned adapter's HTTP client is closed in a finally block.
    """
    sources = source_factory(body.greenhouse_boards, body.lever_companies)
    try:
        created_postings, logs = await run_scrape(
            session=session,
            sources=sources,
            filters=body.filters,
            llm=llm if body.extract else None,
            extract=body.extract,
        )
        await session.commit()
    finally:
        for src in sources:
            aclose = getattr(src, "aclose", None)
            if callable(aclose):
                await aclose()

    return ScrapeResponse(
        created=len(created_postings),
        runs=[
            ScrapeRunLogView(
                source=log.source,
                total_listed=log.total_listed,
                total_fetched=log.total_fetched,
                total_failed=log.total_failed,
                total_new=log.total_new,
            )
            for log in logs
        ],
    )
