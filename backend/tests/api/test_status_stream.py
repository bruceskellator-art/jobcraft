"""Tests for GET /api/status-events/stream (SSE endpoint).

Covers:
- Response has Content-Type: text/event-stream
- Emits proposed status events as SSE data: frames (JSON-encoded StatusEventRead)
- Emits a keep-alive comment after events
- Consuming the bounded stream completes without error
- Empty proposed list emits only the keep-alive
"""
from __future__ import annotations

import json
import uuid

import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.application import Application
from app.db.models.job_posting import JobPosting
from app.db.models.status_event import StatusEvent
from app.db.models.user import User
from app.deps import get_current_user, get_token_crypto
from app.email_sync.crypto import TokenCrypto
from app.main import create_app

_FERNET_KEY = Fernet.generate_key().decode()


def _make_user(suffix: str = "sse") -> User:
    return User(id=uuid.uuid4(), email=f"sse-{suffix}@jobcraft.local", name="SSE User")


def _make_job() -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        source="manual",
        source_url="https://ssecorp.com/jobs/1",
        company="ssecorp",
        title="Engineer",
        raw_content="JD",
    )


def _make_app(user_id: uuid.UUID, job_id: uuid.UUID) -> Application:
    return Application(
        id=uuid.uuid4(),
        user_id=user_id,
        job_id=job_id,
        status="submitted",
    )


def _make_proposed_event(application_id: uuid.UUID) -> StatusEvent:
    return StatusEvent(
        id=uuid.uuid4(),
        application_id=application_id,
        email_message_id=None,
        from_status="submitted",
        to_status="rejected",
        classification="rejected",
        confidence=0.92,
        state="proposed",
    )


@pytest_asyncio.fixture
async def sse_client(session: AsyncSession):
    """Test client with a seeded proposed status event for SSE tests."""
    application = create_app()

    crypto = TokenCrypto(_FERNET_KEY)
    user = _make_user()
    job = _make_job()
    app = _make_app(user.id, job.id)
    event = _make_proposed_event(app.id)

    session.add(user)
    session.add(job)
    session.add(app)
    session.add(event)
    await session.flush()

    async def _override_session():
        yield session

    application.dependency_overrides[get_session] = _override_session
    application.dependency_overrides[get_current_user] = lambda: user
    application.dependency_overrides[get_token_crypto] = lambda: crypto

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac, user, event

    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sse_client_empty(session: AsyncSession):
    """Test client with NO proposed events (tests empty stream)."""
    application = create_app()

    crypto = TokenCrypto(_FERNET_KEY)
    user = _make_user(suffix="empty")
    session.add(user)
    await session.flush()

    async def _override_session():
        yield session

    application.dependency_overrides[get_session] = _override_session
    application.dependency_overrides[get_current_user] = lambda: user
    application.dependency_overrides[get_token_crypto] = lambda: crypto

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac

    application.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse(raw: str) -> list[dict | str]:
    """Parse raw SSE text into a list of payloads.

    Returns a list where each element is either:
    - a dict (parsed JSON from ``data:`` lines)
    - the string ": keep-alive" for keep-alive comments
    """
    results: list[dict | str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload_str = line[len("data:"):].strip()
            try:
                results.append(json.loads(payload_str))
            except json.JSONDecodeError:
                results.append(payload_str)
        elif line.startswith(":"):
            results.append(line)
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStatusEventStream:
    async def test_response_content_type_is_event_stream(self, sse_client) -> None:
        client, _, _ = sse_client

        response = await client.get("/api/status-events/stream")

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    async def test_stream_emits_proposed_events(self, sse_client) -> None:
        client, user, event = sse_client

        response = await client.get("/api/status-events/stream")

        assert response.status_code == 200
        items = _parse_sse(response.text)

        # Must contain at least one data frame
        data_frames = [item for item in items if isinstance(item, dict)]
        assert len(data_frames) >= 1

        # First data frame should be our proposed event
        frame = data_frames[0]
        assert frame["state"] == "proposed"
        assert frame["to_status"] == "rejected"
        assert frame["application_id"] == str(event.application_id)

    async def test_stream_emits_keep_alive_comment(self, sse_client) -> None:
        client, _, _ = sse_client

        response = await client.get("/api/status-events/stream")

        assert response.status_code == 200
        items = _parse_sse(response.text)

        # Must contain at least one keep-alive comment
        comments = [item for item in items if isinstance(item, str) and "keep-alive" in item]
        assert len(comments) >= 1

    async def test_stream_event_schema_matches_status_event_read(self, sse_client) -> None:
        client, _, event = sse_client

        response = await client.get("/api/status-events/stream")

        assert response.status_code == 200
        data_frames = [
            item for item in _parse_sse(response.text) if isinstance(item, dict)
        ]
        assert len(data_frames) >= 1
        frame = data_frames[0]

        # Validate expected StatusEventRead fields
        required_fields = {
            "id", "application_id", "from_status", "to_status",
            "classification", "confidence", "state", "created_at",
        }
        for field in required_fields:
            assert field in frame, f"Missing field: {field}"

        # Privacy: no token fields
        assert "oauth_token_enc" not in frame
        assert "token" not in frame

    async def test_stream_completes_for_empty_proposed_list(
        self, sse_client_empty
    ) -> None:
        client = sse_client_empty

        response = await client.get("/api/status-events/stream")

        # Should complete without error even with no proposed events
        assert response.status_code == 200
        items = _parse_sse(response.text)
        data_frames = [item for item in items if isinstance(item, dict)]
        assert data_frames == []  # no proposed events

        # Still emits keep-alive
        comments = [item for item in items if isinstance(item, str) and "keep-alive" in item]
        assert len(comments) >= 1

    async def test_stream_is_bounded_and_terminates(self, sse_client) -> None:
        """max_iterations=1 (default) ensures the stream closes after one poll."""
        client, _, _ = sse_client

        # This should return (not block indefinitely) with default max_iterations=1
        response = await client.get("/api/status-events/stream?max_iterations=1")

        assert response.status_code == 200
        # Response body is non-empty
        assert len(response.text) > 0

    async def test_stream_oauth_token_enc_never_returned(self, sse_client) -> None:
        client, _, _ = sse_client

        response = await client.get("/api/status-events/stream")

        assert "oauth_token_enc" not in response.text
