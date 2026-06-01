"""API tests for the Eval admin endpoints.

Covers:
- POST /api/admin/evals/run        — runs resume_quality_v1, returns EvalRunRead
- GET  /api/admin/evals            — lists the persisted run
- GET  /api/admin/evals/{id}       — returns run detail
- GET  /api/admin/evals/{unknown}  — 404
- POST /run with invalid suite_name (path traversal, unknown suite) → 400/404
"""

from __future__ import annotations

import json
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db.models  # noqa: F401 — ensure all models are registered
from app.db.base import Base, get_session, make_session_factory
from app.deps import (
    get_embedding_client,
    get_llm_factory,
    get_session_factory,
    get_vector_store,
)
from app.embeddings.fake import FakeEmbeddingAdapter
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.main import create_app
from app.vectorstore.memory import InMemoryVectorStore

# ---------------------------------------------------------------------------
# Canned mock responses (mirrors test_runner.py)
# ---------------------------------------------------------------------------

_RESUME_MD = (
    "# Eval Candidate\n\n"
    "- Built AI systems using Python and machine learning techniques.\n"
    "- Led cross-functional team delivering product improvements.\n"
    "- Deployed scalable infrastructure handling 1M requests/day.\n"
    "- Applied Python, SQL, and data engineering skills across projects.\n"
)

_GROUNDEDNESS_JSON = json.dumps({
    "claims": [
        {"text": "Built AI systems", "experience_id": None, "grounded": True},
    ],
    "grounded_ratio": 1.0,
    "ungrounded": [],
})

_JUDGE_JSON = json.dumps({"score": 0.85, "rationale": "Good quality resume"})


def _mock_fn(prompt: str) -> str:
    p = prompt.lower()
    if "anti-hallucination" in p:
        return _GROUNDEDNESS_JSON
    if "expert evaluator" in p:
        return _JUDGE_JSON
    return json.dumps({"markdown": _RESUME_MD})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def eval_engine():
    """Fresh in-memory SQLite engine with all tables created."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def eval_client(eval_engine):
    """Test client with all eval-relevant deps overridden.

    - get_session        → in-memory SQLite session (for GET list/get endpoints)
    - get_session_factory → in-memory SQLite factory (for POST /run — runner uses this)
    - get_llm_factory    → MockAdapter factory
    - get_embedding_client → FakeEmbeddingAdapter
    - get_vector_store   → InMemoryVectorStore
    """
    application = create_app()

    test_factory: async_sessionmaker[AsyncSession] = make_session_factory(eval_engine)

    # Shared MockAdapter — the llm_factory binds it to each per-case session.
    adapter = MockAdapter(fn=_mock_fn)

    async def _override_session():
        async with test_factory() as session:
            yield session

    def _override_session_factory() -> async_sessionmaker[AsyncSession]:
        return test_factory

    def _override_llm_factory():
        def _factory(session: AsyncSession) -> LLMClient:
            return LLMClient(session=session, adapter=adapter)
        return _factory

    def _override_embed():
        return FakeEmbeddingAdapter(dim=64)

    def _override_store():
        return InMemoryVectorStore()

    application.dependency_overrides[get_session] = _override_session
    application.dependency_overrides[get_session_factory] = _override_session_factory
    application.dependency_overrides[get_llm_factory] = _override_llm_factory
    application.dependency_overrides[get_embedding_client] = _override_embed
    application.dependency_overrides[get_vector_store] = _override_store

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac

    application.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: POST /api/admin/evals/run
# ---------------------------------------------------------------------------


class TestRunEvalSuite:
    async def test_run_resume_quality_v1_returns_eval_run_read(self, eval_client) -> None:
        """POST /run with resume_quality_v1 should return a valid EvalRunRead."""
        response = await eval_client.post(
            "/api/admin/evals/run",
            json={"suite_name": "resume_quality_v1"},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert "id" in body
        assert body["suite_name"] == "resume_quality_v1"
        assert "aggregate_scores" in body
        assert "pass_rate" in body["aggregate_scores"]
        assert "results" in body
        assert isinstance(body["results"], list)
        assert len(body["results"]) >= 1
        assert "started_at" in body
        assert "completed_at" in body

    async def test_run_persists_aggregate_scores(self, eval_client) -> None:
        """The persisted EvalRun should contain aggregate scores."""
        response = await eval_client.post(
            "/api/admin/evals/run",
            json={"suite_name": "resume_quality_v1"},
        )

        assert response.status_code == 200
        body = response.json()
        aggregate = body["aggregate_scores"]
        assert isinstance(aggregate, dict)
        assert "pass_rate" in aggregate
        assert 0.0 <= aggregate["pass_rate"] <= 1.0

    async def test_run_invalid_suite_name_path_traversal_returns_400(
        self, eval_client
    ) -> None:
        """suite_name with path-traversal characters must be rejected with 400."""
        for bad_name in ["../etc/passwd", "../../secret", "foo/bar", "foo..bar"]:
            response = await eval_client.post(
                "/api/admin/evals/run",
                json={"suite_name": bad_name},
            )
            assert response.status_code in (400, 422), (
                f"Expected 400 or 422 for suite_name={bad_name!r}, "
                f"got {response.status_code}: {response.text}"
            )

    async def test_run_unknown_suite_returns_404(self, eval_client) -> None:
        """suite_name that doesn't match a YAML file should return 404."""
        response = await eval_client.post(
            "/api/admin/evals/run",
            json={"suite_name": "nonexistent_suite_xyz"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests: GET /api/admin/evals
# ---------------------------------------------------------------------------


class TestListEvalRuns:
    async def test_list_shows_persisted_run(self, eval_client) -> None:
        """After a run, GET /api/admin/evals should include that run."""
        # Trigger a run first
        run_response = await eval_client.post(
            "/api/admin/evals/run",
            json={"suite_name": "resume_quality_v1"},
        )
        assert run_response.status_code == 200
        run_id = run_response.json()["id"]

        # List
        list_response = await eval_client.get("/api/admin/evals")

        assert list_response.status_code == 200
        runs = list_response.json()
        assert isinstance(runs, list)
        assert len(runs) >= 1
        ids = [r["id"] for r in runs]
        assert run_id in ids

    async def test_list_returns_empty_before_any_run(self, eval_client) -> None:
        """Before any run, GET /api/admin/evals returns an empty list."""
        response = await eval_client.get("/api/admin/evals")

        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Tests: GET /api/admin/evals/{run_id}
# ---------------------------------------------------------------------------


class TestGetEvalRun:
    async def test_get_run_returns_detail(self, eval_client) -> None:
        """GET /{run_id} should return the full EvalRunRead for a known run."""
        run_response = await eval_client.post(
            "/api/admin/evals/run",
            json={"suite_name": "resume_quality_v1"},
        )
        assert run_response.status_code == 200
        run_id = run_response.json()["id"]

        detail_response = await eval_client.get(f"/api/admin/evals/{run_id}")

        assert detail_response.status_code == 200
        body = detail_response.json()
        assert body["id"] == run_id
        assert body["suite_name"] == "resume_quality_v1"
        assert "results" in body
        assert "aggregate_scores" in body

    async def test_get_unknown_run_returns_404(self, eval_client) -> None:
        """GET /{unknown_id} should return 404."""
        unknown_id = str(uuid.uuid4())
        response = await eval_client.get(f"/api/admin/evals/{unknown_id}")

        assert response.status_code == 404
