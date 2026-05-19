from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.main import create_app


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncClient:  # type: ignore[misc]
    """Async test client with get_session overridden to use the test DB session."""
    application = create_app()

    async def _override_session():  # type: ignore[return]
        yield session

    application.dependency_overrides[get_session] = _override_session
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac
    application.dependency_overrides.clear()


_VALID_PAYLOAD = {
    "kind": "work",
    "title": "Software Engineer",
    "organization": "Acme Corp",
    "content": "Built things.",
    "tags": ["python", "fastapi"],
}


class TestCreateExperienceItem:
    """POST /api/experience"""

    async def test_create_returns_201(self, client: AsyncClient) -> None:
        # Arrange
        payload = _VALID_PAYLOAD

        # Act
        response = await client.post("/api/experience", json=payload)

        # Assert
        assert response.status_code == 201

    async def test_create_returns_correct_body_shape(self, client: AsyncClient) -> None:
        # Arrange
        payload = _VALID_PAYLOAD

        # Act
        response = await client.post("/api/experience", json=payload)

        # Assert
        body = response.json()
        assert body["kind"] == "work"
        assert body["title"] == "Software Engineer"
        assert body["organization"] == "Acme Corp"
        assert body["content"] == "Built things."
        assert body["tags"] == ["python", "fastapi"]
        assert "id" in body
        assert "user_id" in body

    async def test_create_rejects_empty_content(self, client: AsyncClient) -> None:
        # Arrange
        payload = {**_VALID_PAYLOAD, "content": ""}

        # Act
        response = await client.post("/api/experience", json=payload)

        # Assert
        assert response.status_code == 422

    async def test_create_rejects_invalid_kind(self, client: AsyncClient) -> None:
        # Arrange
        payload = {**_VALID_PAYLOAD, "kind": "hobby"}

        # Act
        response = await client.post("/api/experience", json=payload)

        # Assert
        assert response.status_code == 422


class TestListExperienceItems:
    """GET /api/experience"""

    async def test_list_returns_created_items(self, client: AsyncClient) -> None:
        # Arrange
        await client.post("/api/experience", json=_VALID_PAYLOAD)
        await client.post(
            "/api/experience",
            json={**_VALID_PAYLOAD, "kind": "project", "title": "Side project"},
        )

        # Act
        response = await client.get("/api/experience")

        # Assert
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2

    async def test_list_returns_empty_for_new_user(self, client: AsyncClient) -> None:
        # Arrange — no items created yet

        # Act
        response = await client.get("/api/experience")

        # Assert
        assert response.status_code == 200
        assert response.json() == []


class TestGetExperienceItem:
    """GET /api/experience/{item_id}"""

    async def test_get_returns_item(self, client: AsyncClient) -> None:
        # Arrange
        created = (await client.post("/api/experience", json=_VALID_PAYLOAD)).json()
        item_id = created["id"]

        # Act
        response = await client.get(f"/api/experience/{item_id}")

        # Assert
        assert response.status_code == 200
        assert response.json()["id"] == item_id

    async def test_get_missing_item_returns_404(self, client: AsyncClient) -> None:
        # Arrange
        missing_id = "00000000-0000-0000-0000-000000000000"

        # Act
        response = await client.get(f"/api/experience/{missing_id}")

        # Assert
        assert response.status_code == 404


class TestUpdateExperienceItem:
    """PATCH /api/experience/{item_id}"""

    async def test_patch_updates_field(self, client: AsyncClient) -> None:
        # Arrange
        created = (await client.post("/api/experience", json=_VALID_PAYLOAD)).json()
        item_id = created["id"]

        # Act
        response = await client.patch(
            f"/api/experience/{item_id}", json={"title": "Senior Engineer"}
        )

        # Assert
        assert response.status_code == 200
        assert response.json()["title"] == "Senior Engineer"

    async def test_patch_missing_item_returns_404(self, client: AsyncClient) -> None:
        # Arrange
        missing_id = "00000000-0000-0000-0000-000000000000"

        # Act
        response = await client.patch(
            f"/api/experience/{missing_id}", json={"title": "x"}
        )

        # Assert
        assert response.status_code == 404

    async def test_patch_does_not_change_unset_fields(self, client: AsyncClient) -> None:
        # Arrange
        created = (await client.post("/api/experience", json=_VALID_PAYLOAD)).json()
        item_id = created["id"]

        # Act — only update title
        await client.patch(f"/api/experience/{item_id}", json={"title": "New Title"})
        response = await client.get(f"/api/experience/{item_id}")

        # Assert — content unchanged
        assert response.json()["content"] == "Built things."


class TestDeleteExperienceItem:
    """DELETE /api/experience/{item_id}"""

    async def test_delete_returns_204(self, client: AsyncClient) -> None:
        # Arrange
        created = (await client.post("/api/experience", json=_VALID_PAYLOAD)).json()
        item_id = created["id"]

        # Act
        response = await client.delete(f"/api/experience/{item_id}")

        # Assert
        assert response.status_code == 204

    async def test_deleted_item_returns_404_on_get(self, client: AsyncClient) -> None:
        # Arrange
        created = (await client.post("/api/experience", json=_VALID_PAYLOAD)).json()
        item_id = created["id"]
        await client.delete(f"/api/experience/{item_id}")

        # Act
        response = await client.get(f"/api/experience/{item_id}")

        # Assert
        assert response.status_code == 404

    async def test_delete_missing_item_returns_404(self, client: AsyncClient) -> None:
        # Arrange
        missing_id = "00000000-0000-0000-0000-000000000000"

        # Act
        response = await client.delete(f"/api/experience/{missing_id}")

        # Assert
        assert response.status_code == 404


class TestOwnershipIsolation:
    """Items created by one user must not be visible to another."""

    async def test_item_not_visible_to_different_user(self, session: AsyncSession) -> None:
        # Arrange — create item as user A (dev user created by first client)
        from app.db.base import get_session as _get_session
        from app.db.models.user import User
        from app.main import create_app as _create_app

        app_a = _create_app()

        async def _session_a():  # type: ignore[return]
            yield session

        app_a.dependency_overrides[_get_session] = _session_a

        async with AsyncClient(
            transport=ASGITransport(app=app_a), base_url="http://test"
        ) as client_a:
            created = (
                await client_a.post("/api/experience", json=_VALID_PAYLOAD)
            ).json()
            item_id = created["id"]

        app_a.dependency_overrides.clear()

        # Override get_current_user on a separate app instance to return a different user
        from app.deps import get_current_user

        app_b = _create_app()

        async def _session_b():  # type: ignore[return]
            yield session

        import uuid

        other_user = User(
            id=uuid.uuid4(), email="other@jobcraft.local", name="Other User"
        )
        session.add(other_user)
        await session.flush()

        async def _other_user():
            return other_user

        app_b.dependency_overrides[_get_session] = _session_b
        app_b.dependency_overrides[get_current_user] = _other_user

        async with AsyncClient(
            transport=ASGITransport(app=app_b), base_url="http://test"
        ) as client_b:
            # Act
            response = await client_b.get(f"/api/experience/{item_id}")

        app_b.dependency_overrides.clear()

        # Assert — other user cannot see user A's item
        assert response.status_code == 404
