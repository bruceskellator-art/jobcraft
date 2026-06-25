"""API tests for match endpoints.

Covers:
- GET /api/jobs/{id}/match  — computes + returns MatchRead; 404 for unknown job
- POST /api/match/run       — returns matched count
- GET /api/jobs             — includes match for matched jobs, null otherwise
"""

from __future__ import annotations

import json
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.experience_item import ExperienceItem
from app.db.models.user import User
from app.deps import (
    get_current_user,
    get_embedding_client,
    get_llm_client,
    get_vector_store,
)
from app.embeddings.fake import FakeEmbeddingAdapter
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.main import create_app
from app.scrapers.types import JobFilters, RawJobPosting
from app.vectorstore.memory import InMemoryVectorStore

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_MATCH_RESULT = {
    "overall_score": 0.82,
    "dimension_scores": {"skills": 0.9, "seniority": 0.8, "domain": 0.8, "culture": 0.8},
    "gaps": [{"skill": "kubernetes", "severity": "high", "rationale": "Not in experience."}],
    "rationale": "Good overall fit.",
    "matched_experiences": [],
}
_MATCH_JSON = json.dumps(_MATCH_RESULT)

_RAW_JOB = RawJobPosting(
    source="greenhouse:acme",
    source_url="https://boards.greenhouse.io/acme/jobs/1",
    source_id="gh-1",
    company="Acme",
    title="Backend Engineer",
    location="Remote",
    remote_policy="remote",
    raw_content="Python backend engineer role.",
)


class _FakeSource:
    def __init__(self, name: str, postings: list[RawJobPosting]) -> None:
        self.name = name
        self._postings = postings

    async def list_jobs(self, filters: JobFilters):
        for p in self._postings:
            yield p

    async def fetch_job(self, source_id: str) -> RawJobPosting:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def match_client(session: AsyncSession):
    """Test client with all deps overridden: session, user, llm, embed, store."""
    application = create_app()

    # Fixed test user seeded directly into the session
    user = User(id=uuid.uuid4(), email="test@jobcraft.local", name="Test User")
    session.add(user)
    item = ExperienceItem(
        id=uuid.uuid4(),
        user_id=user.id,
        kind="work",
        content="Python backend development with FastAPI and PostgreSQL.",
    )
    session.add(item)
    await session.flush()

    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()

    # MockAdapter that returns a fresh copy of _MATCH_JSON on every call
    # by using fn= so it never runs out of canned responses.
    adapter = MockAdapter(fn=lambda _prompt: _MATCH_JSON)
    llm_client = LLMClient(session=session, adapter=adapter)

    async def _override_session():
        yield session

    def _override_user():
        return user

    def _override_embed():
        return embed

    def _override_store():
        return store

    def _override_llm():
        return llm_client

    def _fake_source_factory():
        def _build(greenhouse_boards, lever_companies, mcf_keywords=None, linkedin_keywords=None):
            sources = []
            for board in greenhouse_boards:
                sources.append(_FakeSource(f"greenhouse:{board}", [_RAW_JOB]))
            return sources
        return _build

    from app.deps import get_source_factory

    application.dependency_overrides[get_session] = _override_session
    application.dependency_overrides[get_current_user] = _override_user
    application.dependency_overrides[get_embedding_client] = _override_embed
    application.dependency_overrides[get_vector_store] = _override_store
    application.dependency_overrides[get_llm_client] = _override_llm
    application.dependency_overrides[get_source_factory] = _fake_source_factory

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac, user

    application.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: GET /api/jobs/{id}/match
# ---------------------------------------------------------------------------


class TestGetJobMatch:
    async def test_computes_and_returns_match_read(self, match_client) -> None:
        client, user = match_client

        # Seed a job via scrape
        await client.post(
            "/api/jobs/scrape",
            json={"greenhouse_boards": ["acme"], "lever_companies": [], "filters": {}},
        )
        jobs = (await client.get("/api/jobs")).json()
        job_id = jobs[0]["id"]

        # Act
        response = await client.get(f"/api/jobs/{job_id}/match")

        # Assert
        assert response.status_code == 200
        body = response.json()
        assert "overall_score" in body
        assert "dimension_scores" in body
        assert "gaps" in body
        assert "rationale" in body
        assert abs(body["overall_score"] - 0.82) < 1e-3

    async def test_returns_404_for_unknown_job(self, match_client) -> None:
        client, _ = match_client
        missing_id = str(uuid.uuid4())

        response = await client.get(f"/api/jobs/{missing_id}/match")

        assert response.status_code == 404

    async def test_match_is_idempotent(self, match_client) -> None:
        client, _ = match_client

        await client.post(
            "/api/jobs/scrape",
            json={"greenhouse_boards": ["acme"], "lever_companies": [], "filters": {}},
        )
        jobs = (await client.get("/api/jobs")).json()
        job_id = jobs[0]["id"]

        r1 = await client.get(f"/api/jobs/{job_id}/match")
        r2 = await client.get(f"/api/jobs/{job_id}/match")

        assert r1.status_code == 200
        assert r2.status_code == 200
        # Same row updated — scores are equal
        assert r1.json()["overall_score"] == r2.json()["overall_score"]


# ---------------------------------------------------------------------------
# Tests: POST /api/match/run
# ---------------------------------------------------------------------------


class TestRunMatch:
    async def test_returns_matched_count(self, match_client) -> None:
        client, _ = match_client

        # Seed one job
        await client.post(
            "/api/jobs/scrape",
            json={"greenhouse_boards": ["acme"], "lever_companies": [], "filters": {}},
        )

        # Act
        response = await client.post("/api/match/run", json={"limit": 50})

        # Assert
        assert response.status_code == 200
        body = response.json()
        assert "matched" in body
        assert body["matched"] == 1

    async def test_run_with_no_jobs_returns_zero(self, match_client) -> None:
        client, _ = match_client

        response = await client.post("/api/match/run", json={"limit": 50})

        assert response.status_code == 200
        assert response.json()["matched"] == 0

    async def test_run_uses_default_limit(self, match_client) -> None:
        client, _ = match_client

        # POST with empty body — limit defaults to 50
        response = await client.post("/api/match/run", json={})

        assert response.status_code == 200
        assert "matched" in response.json()


# ---------------------------------------------------------------------------
# Tests: GET /api/jobs includes match field
# ---------------------------------------------------------------------------


class TestListJobsWithMatch:
    async def test_jobs_list_includes_null_match_before_run(self, match_client) -> None:
        client, _ = match_client

        await client.post(
            "/api/jobs/scrape",
            json={"greenhouse_boards": ["acme"], "lever_companies": [], "filters": {}},
        )

        # No match run yet
        response = await client.get("/api/jobs")

        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 1
        assert jobs[0]["match"] is None

    async def test_jobs_list_includes_match_after_run(self, match_client) -> None:
        client, _ = match_client

        await client.post(
            "/api/jobs/scrape",
            json={"greenhouse_boards": ["acme"], "lever_companies": [], "filters": {}},
        )
        await client.post("/api/match/run", json={"limit": 50})

        response = await client.get("/api/jobs")

        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 1
        match = jobs[0]["match"]
        assert match is not None
        assert "overall_score" in match
        assert abs(match["overall_score"] - 0.82) < 1e-3
