from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:  # type: ignore[misc]
    """Provide an async test client backed by the ASGI app."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    """Tests for GET /health."""

    async def test_health_returns_200(self, client: AsyncClient) -> None:
        # Arrange — client fixture wires up the ASGI transport

        # Act
        response = await client.get("/health")

        # Assert
        assert response.status_code == 200

    async def test_health_returns_status_ok(self, client: AsyncClient) -> None:
        # Arrange
        # Act
        response = await client.get("/health")

        # Assert
        body = response.json()
        assert body["status"] == "ok"

    async def test_health_returns_app_name(self, client: AsyncClient) -> None:
        # Arrange
        # Act
        response = await client.get("/health")

        # Assert
        body = response.json()
        assert "app" in body
        assert isinstance(body["app"], str)
        assert len(body["app"]) > 0

    async def test_health_response_shape(self, client: AsyncClient) -> None:
        # Arrange
        # Act
        response = await client.get("/health")

        # Assert — exactly the keys we document
        body = response.json()
        assert set(body.keys()) == {"status", "app"}


class TestRootEndpoint:
    """Tests for GET /."""

    async def test_root_returns_200(self, client: AsyncClient) -> None:
        # Arrange — client fixture wires up the ASGI transport

        # Act
        response = await client.get("/")

        # Assert
        assert response.status_code == 200

    async def test_root_returns_name(self, client: AsyncClient) -> None:
        # Arrange
        # Act
        response = await client.get("/")

        # Assert
        body = response.json()
        assert "name" in body
        assert isinstance(body["name"], str)
        assert len(body["name"]) > 0

    async def test_root_returns_version(self, client: AsyncClient) -> None:
        # Arrange
        # Act
        response = await client.get("/")

        # Assert
        body = response.json()
        assert "version" in body
        assert body["version"] == "0.1.0"

    async def test_root_response_shape(self, client: AsyncClient) -> None:
        # Arrange
        # Act
        response = await client.get("/")

        # Assert — exactly the keys we document
        body = response.json()
        assert set(body.keys()) == {"name", "version"}
