from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.extractor.service import extract_job
from app.llm.client import LLMClient
from app.repositories.job import JobRepository
from app.scrapers.base import JobSource
from app.scrapers.types import JobFilters, RawJobPosting, ScrapeRunLog

logger = logging.getLogger(__name__)


async def run_scrape(
    session: AsyncSession,
    sources: list[JobSource],
    filters: JobFilters,
    *,
    llm: LLMClient | None = None,
    extract: bool = False,
) -> tuple[list[object], list[ScrapeRunLog]]:
    """Run a scrape across all sources, dedup, optionally extract, and persist.

    For each source:
    - Iterates list_jobs(filters).
    - Skips postings whose (source, source_id) already exist in the DB.
    - Optionally calls extract_job when extract=True and llm is provided.
    - Accumulates a ScrapeRunLog per source.

    A source that raises mid-iteration is caught, logged, and counted in
    total_failed — it never aborts the rest of the run.

    Returns:
        A tuple of (created_postings, per_source_logs).
    """
    repo = JobRepository(session)
    all_created: list[object] = []
    all_logs: list[ScrapeRunLog] = []

    for source in sources:
        total_listed = 0
        total_fetched = 0
        total_failed = 0
        total_new = 0

        try:
            async for raw in source.list_jobs(filters):  # type: ignore[attr-defined]
                total_listed += 1
                posting = await _process_one(
                    raw=raw,
                    repo=repo,
                    session=session,
                    llm=llm,
                    extract=extract,
                )
                if posting is None:
                    # duplicate — skip
                    total_fetched += 1
                    continue
                if posting is _FAILED_SENTINEL:
                    total_failed += 1
                    continue
                total_fetched += 1
                total_new += 1
                all_created.append(posting)
        except Exception:
            logger.exception("run_scrape: source %s raised unexpectedly", source.name)
            total_failed += 1

        all_logs.append(
            ScrapeRunLog(
                source=source.name,
                total_listed=total_listed,
                total_fetched=total_fetched,
                total_failed=total_failed,
                total_new=total_new,
            )
        )

    return all_created, all_logs


# Sentinel returned by _process_one to signal a non-fatal per-item failure.
_FAILED_SENTINEL = object()


async def _process_one(
    raw: RawJobPosting,
    repo: JobRepository,
    session: AsyncSession,
    llm: LLMClient | None,
    extract: bool,
) -> object | None:
    """Persist one raw posting.

    Returns:
        The created JobPosting on success.
        None if the posting already exists (duplicate).
        _FAILED_SENTINEL if a non-fatal error occurred.
    """
    try:
        if raw.source_id is not None:
            existing = await repo.get_by_source(raw.source, raw.source_id)
            if existing is not None:
                return None

        extracted_dict: dict | None = None
        if extract and llm is not None and raw.raw_content.strip():
            try:
                extracted_job = await extract_job(session, llm, raw.raw_content)
                if extracted_job is not None:
                    extracted_dict = extracted_job.model_dump()
            except Exception:
                logger.warning(
                    "run_scrape: extract_job failed for source=%s source_id=%s",
                    raw.source,
                    raw.source_id,
                )

        return await repo.create_from_raw(raw, extracted_dict)

    except Exception:
        logger.exception(
            "run_scrape: failed to persist posting source=%s source_id=%s",
            raw.source,
            raw.source_id,
        )
        return _FAILED_SENTINEL
