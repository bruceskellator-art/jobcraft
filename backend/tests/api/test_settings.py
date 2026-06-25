from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.main import create_app


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:  # type: ignore[misc]
    """Async test client with the DB session overridden to the test session."""
    application = create_app()

    async def _override_session():  # type: ignore[return]
        yield session

    application.dependency_overrides[get_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac

    application.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ui_prefs_returns_default_when_unset(client: AsyncClient) -> None:
    resp = await client.get("/api/settings/ui-prefs")

    assert resp.status_code == 200
    assert resp.json() == {"theme": "system"}


@pytest.mark.asyncio
async def test_ui_prefs_put_then_get_round_trips(client: AsyncClient) -> None:
    put = await client.put("/api/settings/ui-prefs", json={"theme": "dark"})
    assert put.status_code == 200
    assert put.json() == {"theme": "dark"}

    get = await client.get("/api/settings/ui-prefs")
    assert get.status_code == 200
    assert get.json() == {"theme": "dark"}


@pytest.mark.asyncio
async def test_ui_prefs_rejects_invalid_theme(client: AsyncClient) -> None:
    resp = await client.put("/api/settings/ui-prefs", json={"theme": "neon"})

    assert resp.status_code == 422
