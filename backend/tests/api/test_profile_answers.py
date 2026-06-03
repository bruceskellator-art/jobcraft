"""API integration tests for /api/profile and /api/answers."""
from __future__ import annotations

import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.user import User
from app.deps import get_embedding_client, get_vector_store
from app.embeddings.fake import FakeEmbeddingAdapter
from app.main import create_app
from app.vectorstore.memory import InMemoryVectorStore


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncClient:  # type: ignore[misc]
    """Async test client with session, embed, and store overridden."""
    application = create_app()
    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()

    async def _override_session():  # type: ignore[return]
        yield session

    application.dependency_overrides[get_session] = _override_session
    application.dependency_overrides[get_embedding_client] = lambda: embed
    application.dependency_overrides[get_vector_store] = lambda: store

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac

    application.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Profile field CRUD
# ---------------------------------------------------------------------------


class TestProfileFields:
    async def test_list_fields_initially_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/profile/fields")
        assert response.status_code == 200
        assert response.json() == []

    async def test_put_field_creates_new(self, client: AsyncClient) -> None:
        payload = {"key": "location", "value": "Singapore", "is_knockout": False}
        response = await client.put("/api/profile/fields", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["key"] == "location"
        assert body["value"] == "Singapore"
        assert body["is_knockout"] is False

    async def test_put_field_updates_existing_key(self, client: AsyncClient) -> None:
        payload = {"key": "location", "value": "Singapore", "is_knockout": False}
        first = await client.put("/api/profile/fields", json=payload)
        second = await client.put(
            "/api/profile/fields",
            json={"key": "location", "value": "Kuala Lumpur", "is_knockout": True},
        )
        assert second.status_code == 200
        body = second.json()
        assert body["id"] == first.json()["id"]
        assert body["value"] == "Kuala Lumpur"
        assert body["is_knockout"] is True

    async def test_list_includes_created_fields(self, client: AsyncClient) -> None:
        await client.put(
            "/api/profile/fields",
            json={"key": "location", "value": "Singapore", "is_knockout": False},
        )
        await client.put(
            "/api/profile/fields",
            json={"key": "salary", "value": "120000", "is_knockout": True},
        )
        response = await client.get("/api/profile/fields")
        assert response.status_code == 200
        keys = {f["key"] for f in response.json()}
        assert keys == {"location", "salary"}

    async def test_list_excludes_reserved_autopilot_key(
        self, client: AsyncClient
    ) -> None:
        # Set autopilot (writes reserved key to ProfileField table)
        await client.put("/api/profile/autopilot", json={})
        # List should NOT include __autopilot__
        response = await client.get("/api/profile/fields")
        assert response.status_code == 200
        keys = [f["key"] for f in response.json()]
        assert "__autopilot__" not in keys

    async def test_delete_field_removes_it(self, client: AsyncClient) -> None:
        await client.put(
            "/api/profile/fields",
            json={"key": "location", "value": "Singapore", "is_knockout": False},
        )
        del_response = await client.delete("/api/profile/fields/location")
        assert del_response.status_code == 204
        list_response = await client.get("/api/profile/fields")
        keys = [f["key"] for f in list_response.json()]
        assert "location" not in keys

    async def test_delete_missing_field_returns_404(self, client: AsyncClient) -> None:
        response = await client.delete("/api/profile/fields/nonexistent")
        assert response.status_code == 404

    async def test_put_reserved_key_returns_400(self, client: AsyncClient) -> None:
        response = await client.put(
            "/api/profile/fields",
            json={"key": "__autopilot__", "value": "{}", "is_knockout": False},
        )
        assert response.status_code == 400

    async def test_delete_reserved_key_returns_400(self, client: AsyncClient) -> None:
        response = await client.delete("/api/profile/fields/__autopilot__")
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Autopilot GET/PUT
# ---------------------------------------------------------------------------


class TestAutopilotEndpoints:
    async def test_get_returns_defaults_when_unset(self, client: AsyncClient) -> None:
        response = await client.get("/api/profile/autopilot")
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "selective"
        assert body["min_confidence"] == 0.75
        assert body["daily_cap"] == 80

    async def test_put_then_get_round_trips(self, client: AsyncClient) -> None:
        payload = {
            "mode": "full",
            "auto_submit_sources": ["linkedin_easy_apply"],
            "min_confidence": 0.9,
            "min_fit": 0.6,
            "daily_cap": 40,
        }
        put_response = await client.put("/api/profile/autopilot", json=payload)
        assert put_response.status_code == 200

        get_response = await client.get("/api/profile/autopilot")
        assert get_response.status_code == 200
        body = get_response.json()
        assert body["mode"] == "full"
        assert body["daily_cap"] == 40

    async def test_put_autopilot_twice_updates(self, client: AsyncClient) -> None:
        await client.put("/api/profile/autopilot", json={"mode": "off", "daily_cap": 10})
        await client.put("/api/profile/autopilot", json={"mode": "full", "daily_cap": 200})
        body = (await client.get("/api/profile/autopilot")).json()
        assert body["mode"] == "full"
        assert body["daily_cap"] == 200


# ---------------------------------------------------------------------------
# Answer bank: create → approve → suggest
# ---------------------------------------------------------------------------


class TestAnswerBankEndpoints:
    async def test_list_initially_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/answers")
        assert response.status_code == 200
        assert response.json() == []

    async def test_create_draft(self, client: AsyncClient) -> None:
        payload = {"question": "What is your notice period?", "answer": "One month."}
        response = await client.post("/api/answers", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["question"] == "What is your notice period?"
        assert body["approved"] is False
        assert body["reuse_count"] == 0

    async def test_approve_sets_approved_true(self, client: AsyncClient) -> None:
        created = (
            await client.post(
                "/api/answers",
                json={"question": "What is your notice period?", "answer": "One month."},
            )
        ).json()
        answer_id = created["id"]

        response = await client.post(
            f"/api/answers/{answer_id}/approve", json={"approved": True}
        )
        assert response.status_code == 200
        assert response.json()["approved"] is True

    async def test_approve_missing_returns_404(self, client: AsyncClient) -> None:
        response = await client.post(
            f"/api/answers/{uuid.uuid4()}/approve", json={"approved": True}
        )
        assert response.status_code == 404

    async def test_suggest_returns_approved_answer(self, client: AsyncClient) -> None:
        # Create and approve
        created = (
            await client.post(
                "/api/answers",
                json={
                    "question": "What is your notice period?",
                    "answer": "One month.",
                },
            )
        ).json()
        answer_id = created["id"]
        await client.post(f"/api/answers/{answer_id}/approve", json={"approved": True})

        # Suggest with identical question → should match
        response = await client.get(
            "/api/answers/suggest",
            params={"question": "What is your notice period?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body is not None
        assert body["id"] == answer_id

    async def test_suggest_excludes_unapproved(self, client: AsyncClient) -> None:
        # Create but do NOT approve
        await client.post(
            "/api/answers",
            json={
                "question": "What is your notice period?",
                "answer": "One month.",
            },
        )

        # Suggest — nothing approved, must return null
        response = await client.get(
            "/api/answers/suggest",
            params={"question": "What is your notice period?"},
        )
        assert response.status_code == 200
        assert response.json() is None

    async def test_suggest_returns_null_when_no_answers(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(
            "/api/answers/suggest", params={"question": "Random question?"}
        )
        assert response.status_code == 200
        assert response.json() is None


# ---------------------------------------------------------------------------
# Ownership isolation
# ---------------------------------------------------------------------------


class TestOwnershipIsolation:
    async def test_approve_other_users_answer_returns_404(
        self, session: AsyncSession
    ) -> None:
        # Build two isolated app instances sharing the same DB session
        from app.db.base import get_session as _get_session
        from app.deps import get_current_user as _get_current_user

        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()

        app_a = create_app()

        async def _session_a():  # type: ignore[return]
            yield session

        app_a.dependency_overrides[_get_session] = _session_a
        app_a.dependency_overrides[get_embedding_client] = lambda: embed
        app_a.dependency_overrides[get_vector_store] = lambda: store

        async with AsyncClient(
            transport=ASGITransport(app=app_a), base_url="http://test"
        ) as client_a:
            created = (
                await client_a.post(
                    "/api/answers",
                    json={"question": "Q?", "answer": "A."},
                )
            ).json()
        app_a.dependency_overrides.clear()

        answer_id = created["id"]

        # User B tries to approve user A's answer
        other_user = User(id=uuid.uuid4(), email="other@test.com", name="Other")
        session.add(other_user)
        await session.flush()

        app_b = create_app()

        async def _session_b():  # type: ignore[return]
            yield session

        async def _other_user() -> User:
            return other_user

        app_b.dependency_overrides[_get_session] = _session_b
        app_b.dependency_overrides[_get_current_user] = _other_user
        app_b.dependency_overrides[get_embedding_client] = lambda: embed
        app_b.dependency_overrides[get_vector_store] = lambda: store

        async with AsyncClient(
            transport=ASGITransport(app=app_b), base_url="http://test"
        ) as client_b:
            response = await client_b.post(
                f"/api/answers/{answer_id}/approve", json={"approved": True}
            )

        app_b.dependency_overrides.clear()

        assert response.status_code == 404
