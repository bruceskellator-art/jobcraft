"""API tests for generation endpoints.

Covers:
- POST /api/jobs/{job_id}/generate  → ArtifactRead with scores; 404 for unknown job
- GET  /api/jobs/{job_id}/artifacts → lists artifact for current user + job
- GET  /api/artifacts               → lists all user artifacts
- GET  /api/artifacts/{id}          → 200, 404 unknown, 404 cross-user ownership
- POST /api/artifacts/baseline      → is_baseline artifact with scores; 4xx for non-PDF
"""

from __future__ import annotations

import io
import json
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from reportlab.lib.pagesizes import letter  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.user import User
from app.deps import (
    get_current_user,
    get_embedding_client,
    get_llm_client,
    get_pdf_renderer,
    get_vector_store,
)
from app.embeddings.fake import FakeEmbeddingAdapter
from app.generator.pdf import NullPdfRenderer
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.main import create_app
from app.scrapers.types import JobFilters, RawJobPosting
from app.vectorstore.memory import InMemoryVectorStore

# ---------------------------------------------------------------------------
# Canned LLM responses
# ---------------------------------------------------------------------------

_GENERATED_MARKDOWN = "# John Doe\n\n## Experience\n\n- Worked on Python backend at Acme."

_GENERATED_DOC_JSON = json.dumps({"markdown": _GENERATED_MARKDOWN})

_GROUNDEDNESS_JSON = json.dumps(
    {
        "claims": [
            {
                "text": "Worked on Python backend at Acme.",
                "experience_id": None,
                "grounded": False,
            }
        ],
        "grounded_ratio": 0.0,
        "ungrounded": ["Worked on Python backend at Acme."],
    }
)

_RAW_JOB = RawJobPosting(
    source="greenhouse:acme",
    source_url="https://boards.greenhouse.io/acme/jobs/42",
    source_id="gh-42",
    company="Acme",
    title="Backend Engineer",
    location="Remote",
    remote_policy="remote",
    raw_content="We need a Python backend engineer.",
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


def _make_dispatch_fn() -> callable:
    """Return a fn= for MockAdapter that dispatches by prompt content.

    The generation pipeline makes two LLM calls per artifact:
      1. generate_resume / generate_cover_letter → expects GeneratedDoc JSON
      2. check_groundedness                      → expects GroundednessResult JSON
    """

    def _dispatch(prompt: str) -> str:
        if "anti-hallucination judge" in prompt:
            return _GROUNDEDNESS_JSON
        return _GENERATED_DOC_JSON

    return _dispatch


def _make_small_pdf(text: str = "Jane Doe\n\nSoftware Engineer at Acme") -> bytes:
    """Produce a minimal valid PDF containing extractable text via reportlab."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 720
    for line in text.splitlines():
        c.drawString(72, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def gen_client(session: AsyncSession):
    """Test client with all generation deps overridden."""
    application = create_app()

    user = User(id=uuid.uuid4(), email="gen-test@jobcraft.local", name="Gen Test User")
    session.add(user)
    await session.flush()

    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()
    adapter = MockAdapter(fn=_make_dispatch_fn())
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

    def _override_pdf():
        return NullPdfRenderer()

    def _fake_source_factory():
        def _build(greenhouse_boards, lever_companies):
            return [_FakeSource(f"greenhouse:{b}", [_RAW_JOB]) for b in greenhouse_boards]
        return _build

    from app.deps import get_source_factory

    application.dependency_overrides[get_session] = _override_session
    application.dependency_overrides[get_current_user] = _override_user
    application.dependency_overrides[get_embedding_client] = _override_embed
    application.dependency_overrides[get_vector_store] = _override_store
    application.dependency_overrides[get_llm_client] = _override_llm
    application.dependency_overrides[get_pdf_renderer] = _override_pdf
    application.dependency_overrides[get_source_factory] = _fake_source_factory

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac, user

    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def gen_client_other_user(session: AsyncSession):
    """A second client logged in as a different user (for cross-user ownership tests)."""
    application = create_app()

    other_user = User(id=uuid.uuid4(), email="other@jobcraft.local", name="Other User")
    session.add(other_user)
    await session.flush()

    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()
    adapter = MockAdapter(fn=_make_dispatch_fn())
    llm_client = LLMClient(session=session, adapter=adapter)

    async def _override_session():
        yield session

    def _override_user():
        return other_user

    def _override_embed():
        return embed

    def _override_store():
        return store

    def _override_llm():
        return llm_client

    def _override_pdf():
        return NullPdfRenderer()

    def _fake_source_factory():
        def _build(greenhouse_boards, lever_companies):
            return [_FakeSource(f"greenhouse:{b}", [_RAW_JOB]) for b in greenhouse_boards]
        return _build

    from app.deps import get_source_factory

    application.dependency_overrides[get_session] = _override_session
    application.dependency_overrides[get_current_user] = _override_user
    application.dependency_overrides[get_embedding_client] = _override_embed
    application.dependency_overrides[get_vector_store] = _override_store
    application.dependency_overrides[get_llm_client] = _override_llm
    application.dependency_overrides[get_pdf_renderer] = _override_pdf
    application.dependency_overrides[get_source_factory] = _fake_source_factory

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac, other_user

    application.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_job(client: AsyncClient) -> str:
    """Scrape one job and return its ID."""
    await client.post(
        "/api/jobs/scrape",
        json={"greenhouse_boards": ["acme"], "lever_companies": [], "filters": {}},
    )
    jobs = (await client.get("/api/jobs")).json()
    assert len(jobs) >= 1, "Expected at least one job after scrape"
    return jobs[0]["id"]


# ---------------------------------------------------------------------------
# POST /api/jobs/{job_id}/generate
# ---------------------------------------------------------------------------


class TestGenerateArtifact:
    async def test_generate_resume_returns_artifact_read_with_scores(
        self, gen_client
    ) -> None:
        client, user = gen_client
        job_id = await _seed_job(client)

        response = await client.post(
            f"/api/jobs/{job_id}/generate",
            json={"kind": "resume", "style": {"tone": "balanced", "length": "one_page"}},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["kind"] == "resume"
        assert body["format"] == "markdown"
        assert body["is_baseline"] is False
        assert body["job_id"] == job_id
        assert body["user_id"] == str(user.id)
        assert body["content"] == _GENERATED_MARKDOWN
        assert body["scores"] is not None
        scores = body["scores"]
        assert "fit" in scores
        assert "groundedness" in scores
        assert "ats_keywords" in scores
        assert "quantified_impact" in scores
        assert "clarity" in scores

    async def test_generate_cover_letter_returns_correct_kind(
        self, gen_client
    ) -> None:
        client, _ = gen_client
        job_id = await _seed_job(client)

        response = await client.post(
            f"/api/jobs/{job_id}/generate",
            json={"kind": "cover_letter"},
        )

        assert response.status_code == 201
        assert response.json()["kind"] == "cover_letter"

    async def test_generate_returns_404_for_unknown_job(self, gen_client) -> None:
        client, _ = gen_client
        missing_id = str(uuid.uuid4())

        response = await client.post(
            f"/api/jobs/{missing_id}/generate",
            json={"kind": "resume"},
        )

        assert response.status_code == 404

    async def test_generate_uses_default_style_when_omitted(
        self, gen_client
    ) -> None:
        client, _ = gen_client
        job_id = await _seed_job(client)

        response = await client.post(
            f"/api/jobs/{job_id}/generate",
            json={"kind": "resume"},
        )

        assert response.status_code == 201


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/artifacts
# ---------------------------------------------------------------------------


class TestListJobArtifacts:
    async def test_lists_artifact_after_generate(self, gen_client) -> None:
        client, _ = gen_client
        job_id = await _seed_job(client)

        await client.post(
            f"/api/jobs/{job_id}/generate",
            json={"kind": "resume"},
        )

        response = await client.get(f"/api/jobs/{job_id}/artifacts")

        assert response.status_code == 200
        artifacts = response.json()
        assert len(artifacts) == 1
        assert artifacts[0]["kind"] == "resume"
        assert artifacts[0]["job_id"] == job_id

    async def test_returns_empty_list_when_no_artifacts(self, gen_client) -> None:
        client, _ = gen_client
        job_id = await _seed_job(client)

        response = await client.get(f"/api/jobs/{job_id}/artifacts")

        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# GET /api/artifacts
# ---------------------------------------------------------------------------


class TestListUserArtifacts:
    async def test_lists_all_user_artifacts(self, gen_client) -> None:
        client, _ = gen_client
        job_id = await _seed_job(client)

        await client.post(f"/api/jobs/{job_id}/generate", json={"kind": "resume"})
        await client.post(f"/api/jobs/{job_id}/generate", json={"kind": "cover_letter"})

        response = await client.get("/api/artifacts")

        assert response.status_code == 200
        artifacts = response.json()
        assert len(artifacts) == 2
        kinds = {a["kind"] for a in artifacts}
        assert kinds == {"resume", "cover_letter"}

    async def test_returns_empty_list_when_no_artifacts(self, gen_client) -> None:
        client, _ = gen_client

        response = await client.get("/api/artifacts")

        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# GET /api/artifacts/{artifact_id}
# ---------------------------------------------------------------------------


class TestGetArtifact:
    async def test_returns_artifact_for_owner(self, gen_client) -> None:
        client, _ = gen_client
        job_id = await _seed_job(client)
        gen_resp = await client.post(
            f"/api/jobs/{job_id}/generate", json={"kind": "resume"}
        )
        artifact_id = gen_resp.json()["id"]

        response = await client.get(f"/api/artifacts/{artifact_id}")

        assert response.status_code == 200
        assert response.json()["id"] == artifact_id

    async def test_returns_404_for_unknown_artifact(self, gen_client) -> None:
        client, _ = gen_client
        missing_id = str(uuid.uuid4())

        response = await client.get(f"/api/artifacts/{missing_id}")

        assert response.status_code == 404

    async def test_returns_404_for_cross_user_access(
        self, gen_client, gen_client_other_user
    ) -> None:
        # User A generates an artifact
        client_a, _ = gen_client
        job_id = await _seed_job(client_a)
        gen_resp = await client_a.post(
            f"/api/jobs/{job_id}/generate", json={"kind": "resume"}
        )
        artifact_id = gen_resp.json()["id"]

        # User B tries to access it
        client_b, _ = gen_client_other_user
        response = await client_b.get(f"/api/artifacts/{artifact_id}")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/artifacts/baseline
# ---------------------------------------------------------------------------


class TestUploadBaseline:
    async def test_upload_valid_pdf_returns_baseline_artifact(
        self, gen_client
    ) -> None:
        client, user = gen_client
        pdf_bytes = _make_small_pdf()

        response = await client.post(
            "/api/artifacts/baseline",
            files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["is_baseline"] is True
        assert body["kind"] == "resume"
        assert body["format"] == "markdown"
        assert body["job_id"] is None
        assert body["user_id"] == str(user.id)
        assert body["scores"] is not None
        scores = body["scores"]
        assert "fit" in scores
        assert "groundedness" in scores
        assert "quantified_impact" in scores
        assert "clarity" in scores

    async def test_upload_replaces_existing_baseline(self, gen_client) -> None:
        client, _ = gen_client
        pdf_bytes = _make_small_pdf()

        # Upload twice
        r1 = await client.post(
            "/api/artifacts/baseline",
            files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        )
        r2 = await client.post(
            "/api/artifacts/baseline",
            files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        )

        assert r1.status_code == 201
        assert r2.status_code == 201
        # IDs differ because old one was deleted
        assert r1.json()["id"] != r2.json()["id"]

        # Only one baseline in the user's artifacts
        all_artifacts = (await client.get("/api/artifacts")).json()
        baselines = [a for a in all_artifacts if a["is_baseline"]]
        assert len(baselines) == 1

    async def test_non_pdf_content_type_returns_415(self, gen_client) -> None:
        client, _ = gen_client

        response = await client.post(
            "/api/artifacts/baseline",
            files={"file": ("resume.txt", b"plain text", "text/plain")},
        )

        assert response.status_code == 415

    async def test_empty_file_returns_422(self, gen_client) -> None:
        client, _ = gen_client

        response = await client.post(
            "/api/artifacts/baseline",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )

        assert response.status_code == 422

    async def test_non_pdf_magic_bytes_returns_415(self, gen_client) -> None:
        client, _ = gen_client
        fake_pdf = b"This is not a PDF but claims to be"

        response = await client.post(
            "/api/artifacts/baseline",
            files={"file": ("fake.pdf", fake_pdf, "application/pdf")},
        )

        assert response.status_code == 415
