"""Dispatch strategies for background scrape runs.

Two interchangeable implementations behind a single ``ScrapeDispatcher`` protocol:

- ``ArqScrapeDispatcher``      — enqueues the run onto Redis via arq. The work is
  picked up by a separate ``arq`` worker process, so it scales horizontally and
  survives API restarts. This is the production / "many users" path.
- ``InProcessScrapeDispatcher`` — runs the scrape in the same process via
  ``asyncio.create_task``. Zero infrastructure (no Redis), single-process only.
  Used as the local-dev / no-Docker fallback and in tests.

Both ultimately call ``execute_scrape_run(run_id, ...)``; the only thing that
crosses the boundary is the run id, which the worker uses to load the persisted
request snapshot from the database.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.client import LLMClient
from app.scrapers.base import JobSource
from app.services.scrape import execute_scrape_run

logger = logging.getLogger(__name__)

# arq's well-known function name; the worker registers the task under this name.
SCRAPE_TASK_NAME = "scrape_run_task"

# Strong references to in-flight in-process tasks so they are not garbage-collected
# mid-run (asyncio only holds weak references to tasks).
_background_tasks: set[asyncio.Task] = set()


class ScrapeDispatcher(Protocol):
    """Schedules a previously-persisted scrape run for execution."""

    async def dispatch(self, run_id: uuid.UUID) -> None:
        """Hand the run off for background execution."""
        ...


class ArqScrapeDispatcher:
    """Enqueue scrape runs onto Redis for the arq worker pool to execute."""

    def __init__(self, pool: object) -> None:
        self._pool = pool

    async def dispatch(self, run_id: uuid.UUID) -> None:
        await self._pool.enqueue_job(SCRAPE_TASK_NAME, str(run_id))  # type: ignore[attr-defined]
        logger.info("Enqueued scrape run %s onto arq", run_id)


class InProcessScrapeDispatcher:
    """Run scrape runs in-process as fire-and-forget asyncio tasks."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        source_factory: Callable[..., list[JobSource]],
        llm_factory: Callable[[AsyncSession], LLMClient] | None,
    ) -> None:
        self._session_factory = session_factory
        self._source_factory = source_factory
        self._llm_factory = llm_factory

    async def dispatch(self, run_id: uuid.UUID) -> None:
        coro = execute_scrape_run(
            run_id,
            session_factory=self._session_factory,
            source_factory=self._source_factory,
            llm_factory=self._llm_factory,
        )
        task = asyncio.create_task(coro)
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        logger.info("Scheduled scrape run %s in-process", run_id)
