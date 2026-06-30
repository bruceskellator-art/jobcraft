from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.extractor.service import extract_job
from app.llm.client import LLMClient
from app.repositories.job import JobRepository
from app.repositories.scrape_run import ScrapeRunRepository
from app.scrapers.base import JobSource
from app.scrapers.dedupe import content_hash
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
      When source_id is None, uses content_hash as the dedup key.
    - Optionally calls extract_job when extract=True and llm is provided.
    - Accumulates a ScrapeRunLog per source.

    A source that raises mid-iteration is caught, logged, and counted in
    total_failed — it never aborts the rest of the run.

    Invariant: total_listed == total_fetched + total_failed

    Returns:
        A tuple of (created_postings, per_source_logs).
    """
    repo = JobRepository(session)
    all_created: list[object] = []
    all_logs: list[ScrapeRunLog] = []

    for source in sources:
        # total_fetched = successfully processed items (new + duplicate)
        # total_new     = subset of fetched that were newly persisted
        # total_failed  = items (or source errors) that raised non-fatally
        # Invariant: total_listed == total_fetched + total_failed
        total_listed = 0
        total_fetched = 0
        total_failed = 0
        total_new = 0

        source_error: str | None = None
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
                if posting is _FAILED_SENTINEL:
                    total_failed += 1
                else:
                    # None means duplicate — still counts as fetched
                    total_fetched += 1
                    if posting is not None:
                        total_new += 1
                        all_created.append(posting)
        except Exception as exc:
            logger.exception("run_scrape: source %s raised unexpectedly", source.name)
            total_failed += 1
            source_error = str(exc)

        logger.info(
            "run_scrape: source=%s listed=%d new=%d failed=%d",
            source.name,
            total_listed,
            total_new,
            total_failed,
        )
        all_logs.append(
            ScrapeRunLog(
                source=source.name,
                total_listed=total_listed,
                total_fetched=total_fetched,
                total_failed=total_failed,
                total_new=total_new,
                error=source_error,
            )
        )

    return all_created, all_logs


def _log_to_dict(log: ScrapeRunLog) -> dict:
    """Serialize a ScrapeRunLog into a JSON-storable dict (ScrapeRunLogView shape)."""
    return {
        "source": log.source,
        "total_listed": log.total_listed,
        "total_fetched": log.total_fetched,
        "total_failed": log.total_failed,
        "total_new": log.total_new,
        "error": log.error,
    }


async def execute_scrape_run(
    run_id: uuid.UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    source_factory: Callable[..., list[JobSource]],
    llm_factory: Callable[[AsyncSession], LLMClient] | None = None,
) -> None:
    """Run a scrape in the background, recording lifecycle + results on the ScrapeRun row.

    Reconstructs the request (query, companies, filters, extract flag) from
    the persisted ``ScrapeRun.request`` snapshot, so the only argument the caller —
    whether the in-process scheduler or an arq worker — must carry across the
    boundary is the ``run_id``.

    Owns its own DB session (the request that enqueued it has already returned).
    Never raises: any failure is captured and persisted as status='failed' so the
    UI can surface it. Sources' HTTP clients are always closed.
    """
    from app.schemas.job import ScrapeRequest  # local import avoids an import cycle

    async with session_factory() as session:
        repo = ScrapeRunRepository(session)
        run = await repo.get(run_id)
        if run is None:
            logger.warning("execute_scrape_run: run %s not found; skipping", run_id)
            return

        request = ScrapeRequest.model_validate(run.request or {})
        await repo.mark_running(run_id)
        await session.commit()

        sources: list[JobSource] = []
        try:
            sources = source_factory(request.query, request.companies)
            effective_filters = (
                request.filters.model_copy(update={"keywords": [request.query.strip()]})
                if request.query.strip()
                else request.filters
            )
            llm = llm_factory(session) if (request.extract and llm_factory is not None) else None
            created, logs = await run_scrape(
                session=session,
                sources=sources,
                filters=effective_filters,
                llm=llm,
                extract=request.extract,
            )
            await session.commit()
            await repo.mark_finished(
                run_id,
                status="succeeded",
                total_created=len(created),
                runs=[_log_to_dict(log) for log in logs],
            )
            await session.commit()
        except Exception as exc:
            logger.exception("execute_scrape_run: run %s failed", run_id)
            # The run_scrape transaction may be poisoned — reset before writing failure.
            await session.rollback()
            await repo.mark_finished(run_id, status="failed", error=str(exc))
            await session.commit()
        finally:
            for src in sources:
                aclose = getattr(src, "aclose", None)
                if callable(aclose):
                    await aclose()


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
        The created JobPosting on success (new item).
        None if the posting already exists (duplicate).
        _FAILED_SENTINEL if a non-fatal error occurred.
    """
    try:
        if raw.source_id is not None:
            existing = await repo.get_by_source(raw.source, raw.source_id)
            if existing is not None:
                return None
        else:
            # No source_id — use content hash as dedup key so identical
            # postings aren't double-inserted across runs.
            hash_key = content_hash(raw)
            existing = await repo.get_by_source(raw.source, hash_key)
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

        # When source_id is None, persist the content hash as source_id so
        # future runs can dedup via get_by_source.
        if raw.source_id is None:
            from dataclasses import replace  # local import to avoid top-level cycle

            raw = replace(raw, source_id=content_hash(raw))

        return await repo.create_from_raw(raw, extracted_dict)

    except Exception:
        logger.exception(
            "run_scrape: failed to persist posting source=%s source_id=%s",
            raw.source,
            raw.source_id,
        )
        return _FAILED_SENTINEL
