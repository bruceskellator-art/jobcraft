from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import get_session
from app.db.models.job_posting import JobPosting
from app.db.models.match import Match as MatchModel
from app.db.models.user import User
from app.deps import (
    get_current_user,
    get_llm_client,
    get_llm_factory,
    get_session_factory,
    get_source_factory,
    get_task_scheduler,
)
from app.llm.client import LLMClient
from app.repositories.job import JobRepository
from app.repositories.scrape_run import ScrapeRunRepository
from app.schemas.job import JobPostingRead, ScrapeRequest, ScrapeResponse, ScrapeRunLogView
from app.schemas.match import MatchRead
from app.schemas.scrape_run import ScrapeRunView
from app.scrapers.base import JobSource
from app.services.scrape import execute_scrape_run, run_scrape

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _get_repo(session: AsyncSession = Depends(get_session)) -> JobRepository:  # noqa: B008
    return JobRepository(session)


@router.get("", response_model=list[JobPostingRead])
async def list_jobs(
    source: str | None = None,
    q: str | None = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> list[JobPostingRead]:
    """List job postings with optional source and full-text query filters.

    Each posting includes the current user's latest Match (or null if not matched).
    """
    repo = JobRepository(session)
    pairs: list[tuple[JobPosting, MatchModel | None]] = await repo.list_with_matches(
        current_user.id, source=source, query=q
    )
    out: list[JobPostingRead] = []
    for job, match in pairs:
        read = JobPostingRead.model_validate(job)
        read = read.model_copy(
            update={"match": MatchRead.model_validate(match) if match is not None else None}
        )
        out.append(read)
    return out


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
    source_factory: Callable[..., list[JobSource]] = Depends(get_source_factory),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> ScrapeResponse:
    """Trigger a scrape across Greenhouse, Lever, and/or MyCareersFuture sources.

    Builds JobSource instances via the injected source_factory so tests
    can override it to inject fake sources with no network calls.
    Each owned adapter's HTTP client is closed in a finally block.
    """
    sources = source_factory(
        body.greenhouse_boards, body.lever_companies,
        body.mcf_keywords, body.linkedin_keywords,
    )
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
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),  # noqa: B008
    source_factory: Callable[..., list[JobSource]] = Depends(get_source_factory),  # noqa: B008
    llm_factory: Callable[[AsyncSession], LLMClient] = Depends(get_llm_factory),  # noqa: B008
    schedule: Callable[[Awaitable[None]], None] = Depends(get_task_scheduler),  # noqa: B008
) -> ScrapeRunView:
    """Enqueue a background scrape and return the pending run immediately (202).

    The actual scraping runs in-process as a fire-and-forget task with its own
    DB session; clients poll ``GET /api/jobs/scrape/runs`` for progress/results.
    """
    repo = ScrapeRunRepository(session)
    run = await repo.create(current_user.id, body.model_dump(mode="json"))
    await session.commit()
    view = ScrapeRunView.model_validate(run)

    def _build_sources() -> list[JobSource]:
        return source_factory(
            body.greenhouse_boards, body.lever_companies,
            body.mcf_keywords, body.linkedin_keywords,
        )

    schedule(
        execute_scrape_run(
            run.id,
            session_factory=session_factory,
            build_sources=_build_sources,
            filters=body.filters,
            build_llm=llm_factory if body.extract else None,
            extract=body.extract,
        )
    )
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
