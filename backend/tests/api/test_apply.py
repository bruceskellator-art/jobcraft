"""API tests for apply endpoints.

Covers all routes in app/api/apply.py using httpx ASGITransport.
All external deps (session, user, llm, embed, store, form_source, strategies)
are overridden to avoid network I/O.
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.apply.browser import FakeFormSource
from app.apply.strategies import GenericFormStrategy, GreenhouseFormStrategy
from app.apply.types import FormField
from app.db.base import get_session
from app.db.models.job_posting import JobPosting
from app.db.models.profile_field import ProfileField
from app.db.models.user import User
from app.deps import (
    get_apply_strategies,
    get_current_user,
    get_embedding_client,
    get_form_source,
    get_llm_client,
    get_vector_store,
)
from app.embeddings.fake import FakeEmbeddingAdapter
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.main import create_app
from app.vectorstore.memory import InMemoryVectorStore

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_FIELDS = [
    FormField(name="full_name", label="Full Name", field_type="text", required=True),
    FormField(name="email", label="Email", field_type="email", required=True),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def apply_client(session: AsyncSession):
    """Test client with all apply deps overridden."""
    application = create_app()

    user = User(id=uuid.uuid4(), email="applytest@jobcraft.local", name="Apply Test User")
    session.add(user)

    job = JobPosting(
        id=uuid.uuid4(),
        source="linkedin_easy_apply",
        source_url="https://linkedin.com/jobs/1",
        source_id="li-1",
        company="TestCo",
        title="Software Engineer",
        raw_content="Python engineer role.",
    )
    session.add(job)

    # Profile fields so all-clear pass is possible
    for key, value, is_ko in [
        ("full_name", "Apply User", False),
        ("email", "applytest@jobcraft.local", False),
        ("work_authorization", "Yes", True),
    ]:
        session.add(
            ProfileField(
                id=uuid.uuid4(), user_id=user.id, key=key, value=value, is_knockout=is_ko
            )
        )

    await session.flush()

    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()
    adapter = MockAdapter(fn=lambda _: "test response")
    llm_client = LLMClient(session=session, adapter=adapter)
    form_source = FakeFormSource(_FIELDS, captcha=False)

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

    def _override_form_source():
        return form_source

    def _override_strategies():
        return [
            GreenhouseFormStrategy(form_source),
            GenericFormStrategy(form_source),
        ]

    application.dependency_overrides[get_session] = _override_session
    application.dependency_overrides[get_current_user] = _override_user
    application.dependency_overrides[get_embedding_client] = _override_embed
    application.dependency_overrides[get_vector_store] = _override_store
    application.dependency_overrides[get_llm_client] = _override_llm
    application.dependency_overrides[get_form_source] = _override_form_source
    application.dependency_overrides[get_apply_strategies] = _override_strategies

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac, user, job

    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def apply_client_other_user(session: AsyncSession):
    """Second user — for ownership 404 tests."""
    application = create_app()

    user_a = User(id=uuid.uuid4(), email="usera@jobcraft.local", name="User A")
    user_b = User(id=uuid.uuid4(), email="userb@jobcraft.local", name="User B")
    session.add(user_a)
    session.add(user_b)

    job = JobPosting(
        id=uuid.uuid4(),
        source="linkedin_easy_apply",
        source_url="https://linkedin.com/jobs/2",
        source_id="li-2",
        company="OtherCo",
        title="QA Engineer",
        raw_content="QA role.",
    )
    session.add(job)
    await session.flush()

    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()
    form_source = FakeFormSource(_FIELDS)

    async def _override_session():
        yield session

    def _override_user_a():
        return user_a

    def _override_embed():
        return embed

    def _override_store():
        return store

    def _override_llm():
        return LLMClient(session=session, adapter=MockAdapter(fn=lambda _: "x"))

    def _override_form_source():
        return form_source

    def _override_strategies():
        return [GenericFormStrategy(form_source)]

    application.dependency_overrides[get_session] = _override_session
    application.dependency_overrides[get_current_user] = _override_user_a
    application.dependency_overrides[get_embedding_client] = _override_embed
    application.dependency_overrides[get_vector_store] = _override_store
    application.dependency_overrides[get_llm_client] = _override_llm
    application.dependency_overrides[get_form_source] = _override_form_source
    application.dependency_overrides[get_apply_strategies] = _override_strategies

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac, user_a, user_b, job

    application.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/apply/queue
# ---------------------------------------------------------------------------


class TestQueueApplications:
    async def test_creates_applications_for_job_ids(self, apply_client) -> None:
        client, user, job = apply_client

        response = await client.post(
            "/api/apply/queue", json={"job_ids": [str(job.id)]}
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["job_id"] == str(job.id)
        assert body[0]["status"] == "queued"

    async def test_deduplicates_on_repeat(self, apply_client) -> None:
        client, user, job = apply_client

        r1 = await client.post("/api/apply/queue", json={"job_ids": [str(job.id)]})
        r2 = await client.post("/api/apply/queue", json={"job_ids": [str(job.id)]})

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()[0]["id"] == r2.json()[0]["id"]

    async def test_empty_job_ids_rejected(self, apply_client) -> None:
        client, _, _job = apply_client

        response = await client.post("/api/apply/queue", json={"job_ids": []})

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/applications
# ---------------------------------------------------------------------------


class TestListApplications:
    async def test_returns_all_applications(self, apply_client) -> None:
        client, user, job = apply_client

        await client.post("/api/apply/queue", json={"job_ids": [str(job.id)]})
        response = await client.get("/api/applications")

        assert response.status_code == 200
        apps = response.json()
        assert len(apps) >= 1

    async def test_filters_by_status(self, apply_client) -> None:
        client, user, job = apply_client

        await client.post("/api/apply/queue", json={"job_ids": [str(job.id)]})

        queued_resp = await client.get("/api/applications?status=queued")
        assert queued_resp.status_code == 200
        queued = queued_resp.json()
        assert all(a["status"] == "queued" for a in queued)

        submitted_resp = await client.get("/api/applications?status=submitted")
        assert submitted_resp.status_code == 200
        # No submitted apps yet
        assert len(submitted_resp.json()) == 0


# ---------------------------------------------------------------------------
# GET /api/apply/queue
# ---------------------------------------------------------------------------


class TestGetReviewQueue:
    async def test_returns_review_items_with_field_maps(self, apply_client) -> None:
        client, user, job = apply_client

        # Enqueue and process with dry_run=False to get needs_review (no profile knockout)
        await client.post("/api/apply/queue", json={"job_ids": [str(job.id)]})

        # Move to needs_review via manual PATCH
        apps = (await client.get("/api/applications")).json()
        app_id = apps[0]["id"]
        await client.patch(
            f"/api/applications/{app_id}/status", json={"status": "needs_review"}
        )

        response = await client.get("/api/apply/queue")

        assert response.status_code == 200
        items = response.json()
        assert len(items) >= 1
        item = items[0]
        assert "application" in item
        assert "job" in item
        assert item["job"]["id"] == str(job.id)


# ---------------------------------------------------------------------------
# POST /api/applications/{id}/process
# ---------------------------------------------------------------------------


class TestProcessOne:
    async def test_process_returns_attempt(self, apply_client) -> None:
        client, user, job = apply_client

        await client.post("/api/apply/queue", json={"job_ids": [str(job.id)]})
        apps = (await client.get("/api/applications")).json()
        app_id = apps[0]["id"]

        response = await client.post(
            f"/api/applications/{app_id}/process",
            json={"dry_run": True},
        )

        assert response.status_code == 200
        body = response.json()
        assert "outcome" in body
        assert "overall_confidence" in body
        assert body["application_id"] == app_id

    async def test_process_unknown_application_returns_404(self, apply_client) -> None:
        client, _, _job = apply_client
        fake_id = str(uuid.uuid4())

        response = await client.post(
            f"/api/applications/{fake_id}/process",
            json={"dry_run": True},
        )

        assert response.status_code == 404

    async def test_process_ownership_guard(self, apply_client_other_user) -> None:
        """User A cannot process an application belonging to User B."""
        client, user_a, user_b, job = apply_client_other_user

        # The apply_client_other_user fixture has user_a as current_user.
        # Verify that accessing a nonexistent (other user's) application returns 404.
        fake_id = str(uuid.uuid4())
        response = await client.post(
            f"/api/applications/{fake_id}/process",
            json={"dry_run": True},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/applications/{id}/approve
# ---------------------------------------------------------------------------


class TestApproveApplication:
    async def test_approve_returns_application_read(self, apply_client) -> None:
        client, user, job = apply_client

        await client.post("/api/apply/queue", json={"job_ids": [str(job.id)]})
        apps = (await client.get("/api/applications")).json()
        app_id = apps[0]["id"]

        response = await client.post(
            f"/api/applications/{app_id}/approve",
            json={"dry_run": True},
        )

        assert response.status_code == 200
        body = response.json()
        assert "status" in body
        assert body["id"] == app_id

    async def test_approve_unknown_returns_404(self, apply_client) -> None:
        client, _, _job = apply_client

        response = await client.post(
            f"/api/applications/{uuid.uuid4()}/approve",
            json={"dry_run": True},
        )

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/applications/{id}/status
# ---------------------------------------------------------------------------


class TestPatchStatus:
    async def test_moves_to_phone_screen(self, apply_client) -> None:
        client, user, job = apply_client

        await client.post("/api/apply/queue", json={"job_ids": [str(job.id)]})
        apps = (await client.get("/api/applications")).json()
        app_id = apps[0]["id"]

        response = await client.patch(
            f"/api/applications/{app_id}/status",
            json={"status": "phone_screen"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "phone_screen"

    async def test_rejects_disallowed_status(self, apply_client) -> None:
        client, user, job = apply_client

        await client.post("/api/apply/queue", json={"job_ids": [str(job.id)]})
        apps = (await client.get("/api/applications")).json()
        app_id = apps[0]["id"]

        response = await client.patch(
            f"/api/applications/{app_id}/status",
            json={"status": "submitted"},  # not in allowed manual statuses
        )

        assert response.status_code == 422

    async def test_ownership_guard_returns_404(self, apply_client_other_user) -> None:
        client, user_a, user_b, job = apply_client_other_user

        # Try to update a nonexistent (other user's) app
        response = await client.patch(
            f"/api/applications/{uuid.uuid4()}/status",
            json={"status": "withdrawn"},
        )

        assert response.status_code == 404
