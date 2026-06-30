from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.deps import get_scrape_dispatcher
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


def _fake_source_build(query, companies=None):
    """Source factory that yields one fake posting per company, no network."""
    return [_FakeSource(f"greenhouse:{c}", [_RAW]) for c in companies or []]


class _CapturingDispatcher:
    """Records dispatched run ids instead of executing them in the background.

    Lets tests assert a run was dispatched, then run it deterministically by
    calling execute_scrape_run directly (simulating the arq worker).
    """

    def __init__(self) -> None:
        self.run_ids: list = []

    async def dispatch(self, run_id) -> None:  # noqa: ANN001
        self.run_ids.append(run_id)


@pytest_asyncio.fixture
async def client(session: AsyncSession):  # type: ignore[misc]
    application = create_app()
    dispatcher = _CapturingDispatcher()

    async def _override_session():  # type: ignore[return]
        yield session

    application.dependency_overrides[get_session] = _override_session
    application.dependency_overrides[get_scrape_dispatcher] = lambda: dispatcher

    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
        yield ac, dispatcher

    application.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_enqueue_returns_pending_run(client) -> None:
    ac, _ = client
    resp = await ac.post("/api/jobs/scrape/runs", json={"companies": ["acme"]})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["total_created"] == 0
    assert body["id"]


@pytest.mark.asyncio
async def test_enqueued_run_appears_in_list(client) -> None:
    ac, _ = client
    await ac.post("/api/jobs/scrape/runs", json={"companies": ["acme"]})

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
    ac, dispatcher = client
    enqueue = await ac.post("/api/jobs/scrape/runs", json={"companies": ["acme"]})
    run_id = enqueue.json()["id"]

    # Exactly one run was dispatched; execute it now (simulating the worker).
    assert len(dispatcher.run_ids) == 1
    await execute_scrape_run(
        dispatcher.run_ids[0],
        session_factory=_SameSessionFactory(session),
        source_factory=_fake_source_build,
        llm_factory=None,
    )

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
    run = await repo.create(_USER_ID, {"companies": ["acme"]})
    await session.commit()

    def _explode(*args, **kwargs) -> list:
        raise RuntimeError("boom building sources")

    await execute_scrape_run(
        run.id,
        session_factory=_SameSessionFactory(session),
        source_factory=_explode,
        llm_factory=None,
    )

    refreshed = await repo.get(run.id)
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert "boom" in (refreshed.error or "")


# A fixed user id for the direct-service test (no HTTP layer / current_user).
import uuid as _uuid  # noqa: E402

_USER_ID = _uuid.UUID("11111111-1111-1111-1111-111111111111")
