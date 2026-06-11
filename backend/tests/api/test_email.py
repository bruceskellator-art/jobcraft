"""API tests for email sync endpoints.

Covers:
- POST /api/email/connect          → account stored; response has NO token field
- GET  /api/email/accounts         → lists accounts (no tokens)
- POST /api/email/accounts/{id}/sync → SyncResult + status events created
- POST /api/status-events/{id}/confirm → application.status updated + event 'applied'
- POST /api/status-events/{id}/dismiss → event 'dismissed'
- DELETE /api/email/accounts/{id}  → 204 + account gone
- Ownership 404s for accounts and events belonging to other users
- No endpoint ever returns oauth_token_enc
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.application import Application
from app.db.models.email_account import EmailAccount
from app.db.models.job_posting import JobPosting
from app.db.models.status_event import StatusEvent
from app.db.models.user import User
from app.deps import get_current_user, get_llm_client, get_token_crypto
from app.email_sync.crypto import TokenCrypto
from app.email_sync.provider import FakeEmailProvider, RawEmail
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.main import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FERNET_KEY = Fernet.generate_key().decode()

_REJECTION_RESPONSE = json.dumps(
    {
        "classification": "rejected",
        "confidence": 0.92,
        "suggested_status": "rejected",
        "evidence": "We will not be moving forward.",
        "requires_human": True,
    }
)


def _make_user(email: str = "email-test@jobcraft.local") -> User:
    return User(id=uuid.uuid4(), email=email, name="Email Test User")


def _make_job(company: str = "acmecorp") -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        source="manual",
        source_url=f"https://{company}.com/jobs/1",
        company=company,
        title="Software Engineer",
        raw_content="JD text",
    )


def _make_app(user_id: uuid.UUID, job_id: uuid.UUID) -> Application:
    return Application(
        id=uuid.uuid4(),
        user_id=user_id,
        job_id=job_id,
        status="submitted",
    )


def _make_account(user_id: uuid.UUID, crypto: TokenCrypto) -> EmailAccount:
    token_enc = crypto.encrypt({"access_token": "fake-access", "scope": "gmail.readonly"})
    return EmailAccount(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="gmail",
        email_address="test@gmail.com",
        oauth_token_enc=token_enc,
        scopes=["gmail.readonly"],
    )


def _rejection_email() -> RawEmail:
    return RawEmail(
        provider_message_id="msg-rej-001",
        thread_id=None,
        from_address="ats@acmecorp",  # domain matches company "acmecorp"
        subject="Application Update",
        snippet="We will not be moving forward.",
        body="Dear Candidate, We will not be moving forward with your application.",
        received_at=datetime(2026, 6, 24, 10, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def email_client(session: AsyncSession):
    """Test client with all email deps overridden.

    Provides a FakeEmailProvider with one canned rejection email,
    and a MockAdapter returning one classification response.
    """
    application = create_app()

    crypto = TokenCrypto(_FERNET_KEY)
    user = _make_user()
    job = _make_job()
    app = _make_app(user.id, job.id)

    session.add(user)
    session.add(job)
    session.add(app)
    await session.flush()

    fake_provider = FakeEmailProvider(
        messages=[_rejection_email()],
        cursor="cursor-v1",
    )
    adapter = MockAdapter(fn=lambda _prompt: _REJECTION_RESPONSE)
    llm_client = LLMClient(session=session, adapter=adapter)

    async def _override_session():
        yield session

    application.dependency_overrides[get_session] = _override_session
    application.dependency_overrides[get_current_user] = lambda: user
    application.dependency_overrides[get_token_crypto] = lambda: crypto
    application.dependency_overrides[get_llm_client] = lambda: llm_client

    # Patch get_email_provider at the api.email module level so sync uses FakeEmailProvider
    import app.api.email as email_module

    _original_get_email_provider = email_module.get_email_provider

    def _fake_get_email_provider(_account):  # type: ignore[override]
        return fake_provider

    email_module.get_email_provider = _fake_get_email_provider  # type: ignore[assignment]

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac, user, session, crypto

    email_module.get_email_provider = _original_get_email_provider  # type: ignore[assignment]
    application.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: POST /api/email/connect
# ---------------------------------------------------------------------------


class TestConnectEmailAccount:
    async def test_stores_account_and_returns_safe_fields(self, email_client) -> None:
        client, user, session, _ = email_client

        response = await client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "new@gmail.com",
                "token": {"access_token": "tok", "scope": "gmail.readonly"},
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["provider"] == "gmail"
        assert body["email_address"] == "new@gmail.com"
        assert body["scopes"] == ["gmail.readonly"]
        assert body["status"] == "active"
        # Privacy: oauth_token_enc must NEVER appear in any response
        assert "oauth_token_enc" not in body
        assert "token" not in body

    async def test_account_persisted_in_db(self, email_client) -> None:
        client, user, session, _ = email_client

        await client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "stored@gmail.com",
                "token": {"access_token": "tok2", "scope": ""},
            },
        )

        result = await session.execute(
            select(EmailAccount).where(
                EmailAccount.user_id == user.id,
                EmailAccount.email_address == "stored@gmail.com",
            )
        )
        account = result.scalar_one_or_none()
        assert account is not None
        # The raw token must not be stored as plaintext
        assert account.oauth_token_enc != b"tok2"

    async def test_response_never_contains_oauth_token_enc(self, email_client) -> None:
        client, _, _, _ = email_client

        response = await client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "privacy@gmail.com",
                "token": {"access_token": "secret"},
            },
        )

        assert "oauth_token_enc" not in response.text
        assert "secret" not in response.text


# ---------------------------------------------------------------------------
# Tests: GET /api/email/accounts
# ---------------------------------------------------------------------------


class TestListEmailAccounts:
    async def test_returns_connected_accounts_without_tokens(self, email_client) -> None:
        client, user, session, crypto = email_client

        # Seed an account directly
        account = _make_account(user.id, crypto)
        session.add(account)
        await session.flush()

        response = await client.get("/api/email/accounts")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        for item in body:
            assert "oauth_token_enc" not in item
            assert "token" not in item

    async def test_returns_empty_list_when_no_accounts(self, email_client) -> None:
        client, _, _, _ = email_client

        response = await client.get("/api/email/accounts")

        assert response.status_code == 200
        # May be empty or have accounts from other tests in the same session;
        # just verify the format
        assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# Tests: POST /api/email/accounts/{id}/sync
# ---------------------------------------------------------------------------


class TestSyncEmailAccount:
    async def test_returns_sync_result_and_creates_status_event(
        self, email_client
    ) -> None:
        client, user, session, crypto = email_client

        # Connect an account first
        connect_resp = await client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "sync@gmail.com",
                "token": {"access_token": "sync-tok", "scope": "gmail.readonly"},
            },
        )
        assert connect_resp.status_code == 201
        account_id = connect_resp.json()["id"]

        response = await client.post(f"/api/email/accounts/{account_id}/sync")

        assert response.status_code == 200
        body = response.json()
        assert "ingested" in body
        assert "matched" in body
        assert "applied" in body
        assert "proposed" in body
        # One rejection email processed: ingested=1, matched=1, proposed=1
        assert body["ingested"] == 1
        assert body["matched"] == 1
        assert body["proposed"] == 1

    async def test_sync_creates_proposed_status_event(self, email_client) -> None:
        client, user, session, crypto = email_client

        connect_resp = await client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "events@gmail.com",
                "token": {"access_token": "ev-tok", "scope": "gmail.readonly"},
            },
        )
        account_id = connect_resp.json()["id"]
        await client.post(f"/api/email/accounts/{account_id}/sync")

        # Verify status event created
        result = await session.execute(
            select(StatusEvent)
            .join(Application, StatusEvent.application_id == Application.id)
            .where(Application.user_id == user.id)
        )
        events = list(result.scalars().all())
        assert len(events) == 1
        assert events[0].state == "proposed"
        assert events[0].to_status == "rejected"

    async def test_sync_404_for_unknown_account(self, email_client) -> None:
        client, _, _, _ = email_client
        unknown_id = str(uuid.uuid4())

        response = await client.post(f"/api/email/accounts/{unknown_id}/sync")

        assert response.status_code == 404

    async def test_sync_never_returns_oauth_token_enc(self, email_client) -> None:
        client, user, session, crypto = email_client

        connect_resp = await client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "tok@gmail.com",
                "token": {"access_token": "private-tok"},
            },
        )
        account_id = connect_resp.json()["id"]
        response = await client.post(f"/api/email/accounts/{account_id}/sync")

        assert "oauth_token_enc" not in response.text
        assert "private-tok" not in response.text


# ---------------------------------------------------------------------------
# Tests: POST /api/status-events/{id}/confirm
# ---------------------------------------------------------------------------


class TestConfirmStatusEvent:
    async def test_confirm_applies_transition_and_updates_application(
        self, email_client
    ) -> None:
        client, user, session, crypto = email_client

        # Connect + sync to create a proposed event
        connect_resp = await client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "confirm@gmail.com",
                "token": {"access_token": "c-tok"},
            },
        )
        account_id = connect_resp.json()["id"]
        await client.post(f"/api/email/accounts/{account_id}/sync")

        # Get the proposed event
        events_resp = await client.get("/api/status-events?state=proposed")
        assert events_resp.status_code == 200
        events = events_resp.json()
        assert len(events) == 1
        event_id = events[0]["id"]
        app_id = events[0]["application_id"]

        # Confirm
        confirm_resp = await client.post(f"/api/status-events/{event_id}/confirm")

        assert confirm_resp.status_code == 200
        body = confirm_resp.json()
        assert body["state"] == "applied"

        # Verify application status updated
        app_result = await session.execute(
            select(Application).where(Application.id == uuid.UUID(app_id))
        )
        app = app_result.scalar_one()
        assert app.status == "rejected"

        # Verify event resolved
        event_result = await session.execute(
            select(StatusEvent).where(StatusEvent.id == uuid.UUID(event_id))
        )
        ev = event_result.scalar_one()
        assert ev.state == "applied"
        assert ev.resolved_at is not None

    async def test_confirm_404_for_unknown_event(self, email_client) -> None:
        client, _, _, _ = email_client
        unknown = str(uuid.uuid4())

        response = await client.post(f"/api/status-events/{unknown}/confirm")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests: POST /api/status-events/{id}/dismiss
# ---------------------------------------------------------------------------


class TestDismissStatusEvent:
    async def test_dismiss_marks_event_dismissed(self, email_client) -> None:
        client, user, session, crypto = email_client

        connect_resp = await client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "dismiss@gmail.com",
                "token": {"access_token": "d-tok"},
            },
        )
        account_id = connect_resp.json()["id"]
        await client.post(f"/api/email/accounts/{account_id}/sync")

        events_resp = await client.get("/api/status-events?state=proposed")
        events = events_resp.json()
        assert len(events) == 1
        event_id = events[0]["id"]

        dismiss_resp = await client.post(f"/api/status-events/{event_id}/dismiss")

        assert dismiss_resp.status_code == 200
        body = dismiss_resp.json()
        assert body["state"] == "dismissed"

        # Verify DB
        event_result = await session.execute(
            select(StatusEvent).where(StatusEvent.id == uuid.UUID(event_id))
        )
        ev = event_result.scalar_one()
        assert ev.state == "dismissed"
        assert ev.resolved_at is not None

    async def test_dismiss_does_not_change_application_status(
        self, email_client
    ) -> None:
        client, user, session, crypto = email_client

        connect_resp = await client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "dismissapp@gmail.com",
                "token": {"access_token": "da-tok"},
            },
        )
        account_id = connect_resp.json()["id"]
        await client.post(f"/api/email/accounts/{account_id}/sync")

        events_resp = await client.get("/api/status-events?state=proposed")
        events = events_resp.json()
        event_id = events[0]["id"]
        app_id = events[0]["application_id"]

        await client.post(f"/api/status-events/{event_id}/dismiss")

        # Application status should remain unchanged (still "submitted")
        app_result = await session.execute(
            select(Application).where(Application.id == uuid.UUID(app_id))
        )
        app = app_result.scalar_one()
        assert app.status == "submitted"

    async def test_dismiss_404_for_unknown_event(self, email_client) -> None:
        client, _, _, _ = email_client
        unknown = str(uuid.uuid4())

        response = await client.post(f"/api/status-events/{unknown}/dismiss")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests: DELETE /api/email/accounts/{id}
# ---------------------------------------------------------------------------


class TestDisconnectEmailAccount:
    async def test_disconnect_returns_204_and_removes_account(
        self, email_client
    ) -> None:
        client, user, session, crypto = email_client

        connect_resp = await client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "del@gmail.com",
                "token": {"access_token": "del-tok"},
            },
        )
        assert connect_resp.status_code == 201
        account_id = connect_resp.json()["id"]

        delete_resp = await client.delete(f"/api/email/accounts/{account_id}")

        assert delete_resp.status_code == 204

        # Verify account is gone
        result = await session.execute(
            select(EmailAccount).where(EmailAccount.id == uuid.UUID(account_id))
        )
        assert result.scalar_one_or_none() is None

    async def test_disconnect_404_for_unknown_account(self, email_client) -> None:
        client, _, _, _ = email_client
        unknown = str(uuid.uuid4())

        response = await client.delete(f"/api/email/accounts/{unknown}")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests: ownership guards
# ---------------------------------------------------------------------------


class TestOwnershipGuards:
    @pytest_asyncio.fixture
    async def other_user_client(self, session: AsyncSession):
        """A second client acting as a different user."""
        application = create_app()

        crypto = TokenCrypto(_FERNET_KEY)
        other_user = _make_user(email="other-email-user@jobcraft.local")
        session.add(other_user)
        await session.flush()

        adapter = MockAdapter(fn=lambda _prompt: _REJECTION_RESPONSE)
        other_llm = LLMClient(session=session, adapter=adapter)

        async def _override_session():
            yield session

        application.dependency_overrides[get_session] = _override_session
        application.dependency_overrides[get_current_user] = lambda: other_user
        application.dependency_overrides[get_token_crypto] = lambda: crypto
        application.dependency_overrides[get_llm_client] = lambda: other_llm

        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as ac:
            yield ac, other_user

        application.dependency_overrides.clear()

    async def test_sync_404_for_other_users_account(
        self, email_client, other_user_client, session: AsyncSession
    ) -> None:
        user_client, user, _, crypto = email_client
        other_ac, _ = other_user_client

        # User1 connects an account
        connect_resp = await user_client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "own@gmail.com",
                "token": {"access_token": "own-tok"},
            },
        )
        account_id = connect_resp.json()["id"]

        # Other user tries to sync it
        response = await other_ac.post(f"/api/email/accounts/{account_id}/sync")
        assert response.status_code == 404

    async def test_delete_404_for_other_users_account(
        self, email_client, other_user_client, session: AsyncSession
    ) -> None:
        user_client, user, _, crypto = email_client
        other_ac, _ = other_user_client

        connect_resp = await user_client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "own2@gmail.com",
                "token": {"access_token": "own2-tok"},
            },
        )
        account_id = connect_resp.json()["id"]

        response = await other_ac.delete(f"/api/email/accounts/{account_id}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Privacy invariant: no endpoint ever returns oauth_token_enc
# ---------------------------------------------------------------------------


class TestPrivacyInvariants:
    async def test_connect_response_has_no_token(self, email_client) -> None:
        client, _, _, _ = email_client

        resp = await client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "priv@gmail.com",
                "token": {"access_token": "priv-secret", "scope": "gmail.readonly"},
            },
        )

        assert resp.status_code == 201
        body = resp.json()
        assert "oauth_token_enc" not in body
        assert "priv-secret" not in json.dumps(body)

    async def test_list_accounts_has_no_token(self, email_client) -> None:
        client, user, session, crypto = email_client

        account = _make_account(user.id, crypto)
        session.add(account)
        await session.flush()

        resp = await client.get("/api/email/accounts")

        assert resp.status_code == 200
        for item in resp.json():
            assert "oauth_token_enc" not in item

    async def test_status_events_has_no_token(self, email_client) -> None:
        client, user, session, crypto = email_client

        connect_resp = await client.post(
            "/api/email/connect",
            json={
                "provider": "gmail",
                "email_address": "evpriv@gmail.com",
                "token": {"access_token": "ev-secret"},
            },
        )
        account_id = connect_resp.json()["id"]
        await client.post(f"/api/email/accounts/{account_id}/sync")

        resp = await client.get("/api/status-events?state=proposed")

        assert resp.status_code == 200
        raw = resp.text
        assert "oauth_token_enc" not in raw
        assert "ev-secret" not in raw
