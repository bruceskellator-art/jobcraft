from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.match import Match as MatchModel
from app.db.models.user import User
from app.deps import (
    get_current_user,
    get_llm_client,
    get_scrape_dispatcher,
    get_source_factory,
)
from app.llm.client import LLMClient
from app.repositories.job import JobRepository
from app.repositories.scrape_run import ScrapeRunRepository
from app.schemas.job import (
    JobDetailRead,
    JobPostingPage,
    JobPostingRead,
    ScrapeRequest,
    ScrapeResponse,
    ScrapeRunLogView,
)
from app.schemas.match import MatchRead
from app.schemas.scrape_run import ScrapeRunView
from app.scrapers.base import JobSource
from app.scrapers.registry import company_names
from app.services.scrape import run_scrape
from app.services.scrape_dispatch import ScrapeDispatcher

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _get_repo(session: AsyncSession = Depends(get_session)) -> JobRepository:  # noqa: B008
    return JobRepository(session)


@router.get("", response_model=JobPostingPage)
async def list_jobs(
    source: str | None = None,
    q: str | None = None,
    company: str | None = None,
    location: str | None = None,
    scored: bool | None = None,
    min_fit: float | None = Query(default=None, ge=0.0, le=1.0),
    max_fit: float | None = Query(default=None, ge=0.0, le=1.0),
    posted_within_days: int | None = Query(default=None, ge=1),
    sort: Literal["recent", "fit"] = "recent",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> JobPostingPage:
    """List job postings with filtering, fit-aware sorting, and pagination.

    Each item embeds the current user's latest Match (or null if not matched).
    Returns a JobPostingPage envelope (items/total/limit/offset).
    """
    repo = JobRepository(session)
    rows, total = await repo.list_page(
        current_user.id,
        source=source,
        query=q,
        company=company,
        location=location,
        scored=scored,
        min_fit=min_fit,
        max_fit=max_fit,
        posted_within_days=posted_within_days,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    items: list[JobPostingRead] = []
    for job, match in rows:
        read = JobPostingRead.model_validate(job)
        read = read.model_copy(
            update={"match": MatchRead.model_validate(match) if match is not None else None}
        )
        items.append(read)
    return JobPostingPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/scrape/companies", response_model=list[str])
async def list_curated_companies(
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> list[str]:
    """Return the sorted list of curated company names for the scrape multiselect."""
    return company_names()


@router.get("/{job_id}", response_model=JobDetailRead)
async def get_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> JobDetailRead:
    """Retrieve a single job posting (with full description) by ID.

    Embeds the user's latest STORED match read-only — it never recomputes, so the
    detail view loads instantly. Scoring happens via POST /api/match/run or the
    on-demand GET /api/jobs/{id}/match endpoint. Returns 404 if not found.
    """
    repo = JobRepository(session)
    posting = await repo.get(job_id)
    if posting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found",
        )
    result = await session.execute(
        select(MatchModel)
        .where(MatchModel.user_id == current_user.id, MatchModel.job_id == job_id)
        .order_by(MatchModel.computed_at.desc().nulls_last())
        .limit(1)
    )
    match = result.scalar_one_or_none()
    read = JobDetailRead.model_validate(posting)
    return read.model_copy(
        update={"match": MatchRead.model_validate(match) if match is not None else None}
    )


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_jobs(
    body: ScrapeRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    source_factory: Callable[..., list[JobSource]] = Depends(get_source_factory),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> ScrapeResponse:
    """Trigger a scrape across Greenhouse, Lever, and/or MyCareersFuture sources.

    Builds JobSource instances via the injected source_factory so tests
    can override it to inject fake sources with no network calls.
    Each owned adapter's HTTP client is closed in a finally block.
    """
    sources = source_factory(body.query, body.companies)
    effective_filters = (
        body.filters.model_copy(update={"keywords": [body.query.strip()]})
        if body.query.strip()
        else body.filters
    )
    try:
        created_postings, logs = await run_scrape(
            session=session,
            sources=sources,
            filters=effective_filters,
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
                error=log.error,
            )
            for log in logs
        ],
    )


@router.post("/scrape/runs", response_model=ScrapeRunView, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_scrape(
    body: ScrapeRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    dispatcher: ScrapeDispatcher = Depends(get_scrape_dispatcher),  # noqa: B008
) -> ScrapeRunView:
    """Enqueue a background scrape and return the pending run immediately (202).

    The run's request is persisted, then dispatched for background execution —
    onto Redis/arq workers in production, or in-process when Redis is unavailable.
    Clients poll ``GET /api/jobs/scrape/runs`` for progress/results.
    """
    repo = ScrapeRunRepository(session)
    run = await repo.create(current_user.id, body.model_dump(mode="json"))
    await session.commit()
    view = ScrapeRunView.model_validate(run)

    await dispatcher.dispatch(run.id)
    return view


@router.get("/scrape/runs", response_model=list[ScrapeRunView])
async def list_scrape_runs(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> list[ScrapeRunView]:
    """List the current user's recent scrape runs, newest first."""
    repo = ScrapeRunRepository(session)
    runs = await repo.list_recent(current_user.id)
    return [ScrapeRunView.model_validate(r) for r in runs]


@router.get("/scrape/runs/{run_id}", response_model=ScrapeRunView)
async def get_scrape_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ScrapeRunView:
    """Return a single scrape run owned by the current user, or 404."""
    repo = ScrapeRunRepository(session)
    run = await repo.get(run_id)
    if run is None or run.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scrape run not found",
        )
    return ScrapeRunView.model_validate(run)
