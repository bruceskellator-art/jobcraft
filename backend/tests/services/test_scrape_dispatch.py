from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.deps import get_scrape_dispatcher
from app.services.scrape_dispatch import (
    SCRAPE_TASK_NAME,
    ArqScrapeDispatcher,
    InProcessScrapeDispatcher,
)


def _request(pool: object | None):
    """Build a minimal stand-in for the FastAPI Request the dependency reads."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(arq_pool=pool)))


def test_dispatcher_uses_arq_when_pool_present() -> None:
    dispatcher = get_scrape_dispatcher(
        _request(object()), session_factory=None, source_factory=None, llm_factory=None
    )
    assert isinstance(dispatcher, ArqScrapeDispatcher)


def test_dispatcher_falls_back_to_inprocess_without_pool() -> None:
    dispatcher = get_scrape_dispatcher(
        _request(None), session_factory=None, source_factory=None, llm_factory=None
    )
    assert isinstance(dispatcher, InProcessScrapeDispatcher)


class _FakePool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def enqueue_job(self, name: str, arg: str) -> None:
        self.calls.append((name, arg))


@pytest.mark.asyncio
async def test_arq_dispatcher_enqueues_job_by_run_id() -> None:
    pool = _FakePool()
    dispatcher = ArqScrapeDispatcher(pool)
    run_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

    await dispatcher.dispatch(run_id)

    assert pool.calls == [(SCRAPE_TASK_NAME, str(run_id))]
