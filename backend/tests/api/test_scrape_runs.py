from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.deps import get_session_factory, get_source_factory, get_task_scheduler
from app.main import create_app
from app.scrapers.types import JobFilters, RawJobPosting
from app.services.scrape import execute_scrape_run

_RAW = RawJobPosting(
    source="greenhouse:acme",
    source_url="https://boards.greenhouse.io/acme/jobs/1",
    source_id="1",
    company="Acme",
    title="Backend Engineer",
    location="Singapore",
    remote_policy=None,
    raw_content="Backend role at Acme",
)


class _FakeSource:
    def __init__(self, name: str, postings: list[RawJobPosting]) -> None:
        self.name = name
        self._postings = postings

    async def list_jobs(self, filters: JobFilters) -> AsyncIterator[RawJobPosting]:
        for p in self._postings:
            yield p


class _SameSessionFactory:
    """A session-factory stand-in that hands the background runner the test session.

    Sidesteps the per-connection nature of in-memory SQLite — the runner writes
    through the same connection the test reads from.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self):  # noqa: ANN204 - returns an async context manager
        session = self._session

        class _Ctx:
            async def __aenter__(self):  # noqa: ANN204
                return session

            async def __aexit__(self, *exc):  # noqa: ANN204
                return False

        return _Ctx()


@pytest_asyncio.fixture
async def captured_scheduler():
    """Capture scheduled coroutines instead of running them in the background."""
    captured: list = []

    def _factory():
        return captured.append

    return captured, _factory


@pytest_asyncio.fixture
async def client(session: AsyncSession, captured_scheduler):  # type: ignore[misc]
    captured, scheduler_factory = captured_scheduler
    application = create_app()

    async def _override_session():  # type: ignore[return]
        yield session

    def _fake_source_factory():
        def _build(greenhouse_boards, lever_companies, mcf_keywords=None, linkedin_keywords=None):
            return [_FakeSource(f"greenhouse:{b}", [_RAW]) for b in greenhouse_boards]

        return _build

    application.dependency_overrides[get_session] = _override_session
    application.dependency_overrides[get_source_factory] = _fake_source_factory
    application.dependency_overrides[get_session_factory] = lambda: _SameSessionFactory(session)
    application.dependency_overrides[get_task_scheduler] = scheduler_factory

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac, captured

    # Close any scheduled-but-never-run coroutines to avoid "never awaited" warnings.
    for coro in captured:
        close = getattr(coro, "close", None)
        if callable(close):
            close()
    application.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_enqueue_returns_pending_run(client) -> None:
    ac, _ = client
    resp = await ac.post("/api/jobs/scrape/runs", json={"greenhouse_boards": ["acme"]})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["total_created"] == 0
    assert body["id"]


@pytest.mark.asyncio
async def test_enqueued_run_appears_in_list(client) -> None:
    ac, _ = client
    await ac.post("/api/jobs/scrape/runs", json={"greenhouse_boards": ["acme"]})

    listed = await ac.get("/api/jobs/scrape/runs")
    assert listed.status_code == 200
    runs = listed.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_get_unknown_run_returns_404(client) -> None:
    ac, _ = client
    resp = await ac.get("/api/jobs/scrape/runs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_background_run_succeeds_and_records_results(client, session) -> None:
    ac, captured = client
    enqueue = await ac.post(
        "/api/jobs/scrape/runs", json={"greenhouse_boards": ["acme"]}
    )
    run_id = enqueue.json()["id"]

    # Exactly one coroutine was scheduled; run it now (deterministically).
    assert len(captured) == 1
    await captured[0]

    fetched = await ac.get(f"/api/jobs/scrape/runs/{run_id}")
    body = fetched.json()
    assert body["status"] == "succeeded"
    assert body["total_created"] == 1
    assert body["runs"][0]["source"] == "greenhouse:acme"
    assert body["runs"][0]["total_new"] == 1
    assert body["finished_at"] is not None


@pytest.mark.asyncio
async def test_execute_scrape_run_marks_failed_on_source_error(session: AsyncSession) -> None:
    from app.repositories.scrape_run import ScrapeRunRepository

    repo = ScrapeRunRepository(session)
    run = await repo.create(_USER_ID, {"greenhouse_boards": ["acme"]})
    await session.commit()

    def _explode() -> list:
        raise RuntimeError("boom building sources")

    await execute_scrape_run(
        run.id,
        session_factory=_SameSessionFactory(session),
        build_sources=_explode,
        filters=JobFilters(),
    )

    refreshed = await repo.get(run.id)
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert "boom" in (refreshed.error or "")


# A fixed user id for the direct-service test (no HTTP layer / current_user).
import uuid as _uuid  # noqa: E402

_USER_ID = _uuid.UUID("11111111-1111-1111-1111-111111111111")
