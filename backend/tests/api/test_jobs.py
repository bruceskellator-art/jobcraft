from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.deps import get_llm_client, get_source_factory
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.main import create_app
from app.scrapers.types import JobFilters, RawJobPosting

# ---------------------------------------------------------------------------
# Fake sources for test injection
# ---------------------------------------------------------------------------

_RAW_GREENHOUSE = RawJobPosting(
    source="greenhouse:acme",
    source_url="https://boards.greenhouse.io/acme/jobs/1",
    source_id="gh-1",
    company="Acme",
    title="Backend Engineer",
    location="Remote",
    remote_policy="remote",
    raw_content="Backend engineer role at Acme.",
)

_RAW_LEVER = RawJobPosting(
    source="lever:beta",
    source_url="https://jobs.lever.co/beta/lv-1",
    source_id="lv-1",
    company="Beta Inc",
    title="Frontend Engineer",
    location="New York",
    remote_policy=None,
    raw_content="Frontend engineer role at Beta Inc.",
)

_VALID_EXTRACTED = {
    "company": "Acme",
    "title": "Backend Engineer",
    "seniority": "mid",
    "location": "Remote",
    "remote_policy": "remote",
    "salary_min_usd": None,
    "salary_max_usd": None,
    "required_skills": ["Python"],
    "preferred_skills": [],
    "responsibilities": [],
    "qualifications": [],
    "culture_signals": [],
    "summary": "Backend role.",
}


class _FakeSource:
    def __init__(self, name: str, postings: list[RawJobPosting]) -> None:
        self.name = name
        self._postings = postings

    async def list_jobs(self, filters: JobFilters) -> AsyncIterator[RawJobPosting]:
        for p in self._postings:
            yield p

    async def fetch_job(self, source_id: str) -> RawJobPosting:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncClient:  # type: ignore[misc]
    """Async test client with get_session, get_source_factory, and get_llm_client overridden."""
    application = create_app()

    async def _override_session():  # type: ignore[return]
        yield session

    def _fake_factory(
        greenhouse_boards: list[str],
        lever_companies: list[str],
        mcf_keywords: list[str] | None = None,
        linkedin_keywords: list[str] | None = None,
    ):
        sources = []
        for board in greenhouse_boards:
            sources.append(_FakeSource(f"greenhouse:{board}", [_RAW_GREENHOUSE]))
        for company in lever_companies:
            sources.append(_FakeSource(f"lever:{company}", [_RAW_LEVER]))
        return sources

    def _override_source_factory():
        return _fake_factory

    def _override_llm_client():
        adapter = MockAdapter(fn=lambda _prompt: json.dumps(_VALID_EXTRACTED))
        return LLMClient(session=session, adapter=adapter)

    application.dependency_overrides[get_session] = _override_session
    application.dependency_overrides[get_source_factory] = _override_source_factory
    application.dependency_overrides[get_llm_client] = _override_llm_client

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac

    application.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: POST /api/jobs/scrape
# ---------------------------------------------------------------------------


class TestScrapeEndpoint:
    """POST /api/jobs/scrape"""

    async def test_scrape_returns_created_count(self, client: AsyncClient) -> None:
        # Arrange
        payload = {
            "greenhouse_boards": ["acme"],
            "lever_companies": [],
            "filters": {},
        }

        # Act
        response = await client.post("/api/jobs/scrape", json=payload)

        # Assert
        assert response.status_code == 200
        body = response.json()
        assert body["created"] == 1
        assert len(body["runs"]) == 1
        assert body["runs"][0]["source"] == "greenhouse:acme"

    async def test_scrape_multiple_sources(self, client: AsyncClient) -> None:
        # Arrange
        payload = {
            "greenhouse_boards": ["acme"],
            "lever_companies": ["beta"],
            "filters": {},
        }

        # Act
        response = await client.post("/api/jobs/scrape", json=payload)

        # Assert
        assert response.status_code == 200
        body = response.json()
        assert body["created"] == 2
        assert len(body["runs"]) == 2

    async def test_scrape_no_sources_returns_zero(self, client: AsyncClient) -> None:
        # Arrange
        payload = {"greenhouse_boards": [], "lever_companies": [], "filters": {}}

        # Act
        response = await client.post("/api/jobs/scrape", json=payload)

        # Assert
        assert response.status_code == 200
        assert response.json()["created"] == 0

    async def test_scrape_dedup_on_second_call(self, client: AsyncClient) -> None:
        # Arrange — first call persists the posting
        payload = {"greenhouse_boards": ["acme"], "lever_companies": [], "filters": {}}
        await client.post("/api/jobs/scrape", json=payload)

        # Act — second call with same source
        response = await client.post("/api/jobs/scrape", json=payload)

        # Assert — nothing new
        assert response.json()["created"] == 0

    async def test_scrape_runs_field_structure(self, client: AsyncClient) -> None:
        # Arrange
        payload = {"greenhouse_boards": ["acme"], "lever_companies": [], "filters": {}}

        # Act
        response = await client.post("/api/jobs/scrape", json=payload)

        # Assert
        run = response.json()["runs"][0]
        assert "source" in run
        assert "total_listed" in run
        assert "total_fetched" in run
        assert "total_failed" in run
        assert "total_new" in run


# ---------------------------------------------------------------------------
# Tests: GET /api/jobs
# ---------------------------------------------------------------------------


class TestListJobsEndpoint:
    """GET /api/jobs"""

    async def test_list_returns_scraped_postings(self, client: AsyncClient) -> None:
        # Arrange — seed via scrape
        await client.post(
            "/api/jobs/scrape",
            json={"greenhouse_boards": ["acme"], "lever_companies": [], "filters": {}},
        )

        # Act
        response = await client.get("/api/jobs")

        # Assert
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["title"] == "Backend Engineer"

    async def test_list_empty_when_no_postings(self, client: AsyncClient) -> None:
        # Arrange — no scrape called

        # Act
        response = await client.get("/api/jobs")

        # Assert
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_filter_by_source(self, client: AsyncClient) -> None:
        # Arrange — seed two sources
        await client.post(
            "/api/jobs/scrape",
            json={
                "greenhouse_boards": ["acme"],
                "lever_companies": ["beta"],
                "filters": {},
            },
        )

        # Act — filter to lever only
        response = await client.get("/api/jobs", params={"source": "lever:beta"})

        # Assert
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["source"] == "lever:beta"

    async def test_list_filter_by_query_matches_title(self, client: AsyncClient) -> None:
        # Arrange
        await client.post(
            "/api/jobs/scrape",
            json={
                "greenhouse_boards": ["acme"],
                "lever_companies": ["beta"],
                "filters": {},
            },
        )

        # Act — search for "Backend"
        response = await client.get("/api/jobs", params={"q": "Backend"})

        # Assert
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["title"] == "Backend Engineer"

    async def test_list_filter_by_query_matches_company(self, client: AsyncClient) -> None:
        # Arrange
        await client.post(
            "/api/jobs/scrape",
            json={
                "greenhouse_boards": ["acme"],
                "lever_companies": ["beta"],
                "filters": {},
            },
        )

        # Act — search for "Beta"
        response = await client.get("/api/jobs", params={"q": "Beta"})

        # Assert
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["company"] == "Beta Inc"

    async def test_list_filter_no_match_returns_empty(self, client: AsyncClient) -> None:
        # Arrange
        await client.post(
            "/api/jobs/scrape",
            json={"greenhouse_boards": ["acme"], "lever_companies": [], "filters": {}},
        )

        # Act
        response = await client.get("/api/jobs", params={"q": "nonexistent-xyz"})

        # Assert
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Tests: GET /api/jobs/{job_id}
# ---------------------------------------------------------------------------


class TestGetJobEndpoint:
    """GET /api/jobs/{job_id}"""

    async def test_get_returns_posting(self, client: AsyncClient) -> None:
        # Arrange — seed one posting
        await client.post(
            "/api/jobs/scrape",
            json={"greenhouse_boards": ["acme"], "lever_companies": [], "filters": {}},
        )
        listing = (await client.get("/api/jobs")).json()
        job_id = listing[0]["id"]

        # Act
        response = await client.get(f"/api/jobs/{job_id}")

        # Assert
        assert response.status_code == 200
        assert response.json()["id"] == job_id

    async def test_get_missing_returns_404(self, client: AsyncClient) -> None:
        # Arrange
        missing_id = "00000000-0000-0000-0000-000000000000"

        # Act
        response = await client.get(f"/api/jobs/{missing_id}")

        # Assert
        assert response.status_code == 404

    async def test_get_returns_correct_fields(self, client: AsyncClient) -> None:
        # Arrange
        await client.post(
            "/api/jobs/scrape",
            json={"greenhouse_boards": ["acme"], "lever_companies": [], "filters": {}},
        )
        listing = (await client.get("/api/jobs")).json()
        job_id = listing[0]["id"]

        # Act
        response = await client.get(f"/api/jobs/{job_id}")

        # Assert
        body = response.json()
        assert body["source"] == "greenhouse:acme"
        assert body["company"] == "Acme"
        assert body["title"] == "Backend Engineer"
        assert "source_url" in body
        assert "scraped_at" in body
