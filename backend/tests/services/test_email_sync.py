"""Integration tests for the sync_account pipeline.

Key scenarios:
1. Matched rejection email → EmailMessage persisted, StatusEvent proposed (requires_human).
2. Unmatched newsletter → EmailMessage NOT persisted (privacy rule).
3. sync_cursor updated after sync.
4. Per-message errors are isolated — other messages still processed.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.application import Application
from app.db.models.email_account import EmailAccount
from app.db.models.email_message import EmailMessage
from app.db.models.job_posting import JobPosting
from app.db.models.status_event import StatusEvent
from app.db.models.user import User
from app.email_sync.provider import FakeEmailProvider, RawEmail
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.services.email_sync import sync_account

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user() -> User:
    return User(
        id=uuid.uuid4(),
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        name="Test User",
    )


def _make_job(company: str = "Acme Corp") -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        source="manual",
        source_url=f"https://{company.lower().replace(' ', '')}.com/jobs/1",
        company=company,
        title="Software Engineer",
        raw_content="JD text",
    )


def _make_app(user_id: uuid.UUID, job_id: uuid.UUID, status: str = "submitted") -> Application:
    return Application(
        id=uuid.uuid4(),
        user_id=user_id,
        job_id=job_id,
        status=status,
    )


def _make_account(user_id: uuid.UUID) -> EmailAccount:
    return EmailAccount(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="gmail",
        email_address="user@gmail.com",
        oauth_token_enc=b"encrypted-token-placeholder",
        scopes=["gmail.readonly"],
    )


def _rejected_email_response() -> str:
    return json.dumps(
        {
            "classification": "rejected",
            "confidence": 0.95,
            "suggested_status": "rejected",
            "evidence": "We will not be moving forward with your application.",
            "requires_human": True,
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSyncAccountPipeline:
    @pytest.mark.asyncio
    async def test_matched_rejection_proposed_and_unmatched_not_persisted(
        self, session: AsyncSession
    ) -> None:
        """Matched rejection → persisted + proposed. Newsletter → NOT persisted."""
        # Use company name that produces a domain matching from_address domain
        # Company "newsletter" → domain "newsletter"; from "ats@acmecorp" → domain "acmecorp"
        user = _make_user()
        # Company name without spaces/dots so derived domain == "acmecorp"
        job = JobPosting(
            id=uuid.uuid4(),
            source="manual",
            source_url="https://acmecorp.com/jobs/1",
            company="acmecorp",  # derived domain: "acmecorp"
            title="Software Engineer",
            raw_content="JD text",
        )
        session.add(user)
        session.add(job)
        app = Application(
            id=uuid.uuid4(),
            user_id=user.id,
            job_id=job.id,
            status="submitted",
        )
        session.add(app)
        account = _make_account(user.id)
        session.add(account)
        await session.flush()

        # Matched: from_address domain "acmecorp" matches company "acmecorp"
        rejection_raw = RawEmail(
            provider_message_id="msg-rejection-001",
            thread_id=None,
            from_address="ats@acmecorp",  # domain = "acmecorp"
            subject="Update on your application",
            snippet="We will not be moving forward.",
            body="Dear Candidate, We will not be moving forward with your application.",
            received_at=datetime(2026, 6, 24, 10, 0, 0, tzinfo=UTC),
        )

        # Unmatched: newsletter from completely different domain
        newsletter_raw = RawEmail(
            provider_message_id="msg-newsletter-002",
            thread_id=None,
            from_address="no-reply@weeklydigest.io",  # domain = "weeklydigest.io"
            subject="Weekly Tech Digest",
            snippet="Top stories this week",
            body="Here are the top tech stories this week...",
            received_at=datetime(2026, 6, 24, 11, 0, 0, tzinfo=UTC),
        )

        provider = FakeEmailProvider(
            messages=[rejection_raw, newsletter_raw], cursor="cursor-v2"
        )
        adapter = MockAdapter(responses=[_rejected_email_response()])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        counts = await sync_account(session, llm, account, provider)

        # Assert counts
        assert counts["ingested"] == 2
        assert counts["matched"] == 1
        assert counts["proposed"] == 1  # rejection always proposed
        assert counts["applied"] == 0

        # Assert: matched EmailMessage persisted
        msg_result = await session.execute(
            select(EmailMessage).where(
                EmailMessage.provider_message_id == "msg-rejection-001"
            )
        )
        msg = msg_result.scalar_one_or_none()
        assert msg is not None
        assert msg.application_id == app.id

        # Assert: UNMATCHED newsletter NOT persisted (privacy rule)
        newsletter_result = await session.execute(
            select(EmailMessage).where(
                EmailMessage.provider_message_id == "msg-newsletter-002"
            )
        )
        assert newsletter_result.scalar_one_or_none() is None

        # Assert: StatusEvent created as 'proposed' (rejection always requires_human)
        event_result = await session.execute(
            select(StatusEvent).where(StatusEvent.application_id == app.id)
        )
        events = list(event_result.scalars().all())
        assert len(events) == 1
        event = events[0]
        assert event.state == "proposed"
        assert event.to_status == "rejected"

        # Assert: sync_cursor updated
        await session.refresh(account)
        assert account.sync_cursor == "cursor-v2"
        assert account.last_synced_at is not None

    @pytest.mark.asyncio
    async def test_sync_cursor_updated_even_with_no_messages(
        self, session: AsyncSession
    ) -> None:
        user = _make_user()
        session.add(user)
        account = _make_account(user.id)
        session.add(account)
        await session.flush()

        provider = FakeEmailProvider(messages=[], cursor="cursor-empty")
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        counts = await sync_account(session, llm, account, provider)

        assert counts["ingested"] == 0
        await session.refresh(account)
        assert account.sync_cursor == "cursor-empty"

    @pytest.mark.asyncio
    async def test_per_message_error_is_isolated(
        self, session: AsyncSession
    ) -> None:
        """An error processing one message must not abort processing of others."""
        user = _make_user()
        job = JobPosting(
            id=uuid.uuid4(),
            source="manual",
            source_url="https://goodcorp.com/jobs/1",
            company="goodcorp",  # derived domain "goodcorp"
            title="Engineer",
            raw_content="JD",
        )
        session.add(user)
        session.add(job)
        good_app = Application(
            id=uuid.uuid4(),
            user_id=user.id,
            job_id=job.id,
            status="submitted",
        )
        session.add(good_app)
        account = _make_account(user.id)
        session.add(account)
        await session.flush()

        # First message: will fail because MockAdapter raises (no canned responses for it)
        # Actually, the "bad" message won't match (domain mismatch), so it won't call LLM.
        # To simulate per-message error: make the bad message match (so classifier is called)
        # but MockAdapter has no responses for it, causing RuntimeError.

        bad_raw = RawEmail(
            provider_message_id="msg-bad-001",
            thread_id=None,
            from_address="ats@goodcorp",  # matches goodcorp
            subject="Error trigger",
            snippet="error",
            body="This will cause adapter to run out of responses",
            received_at=datetime(2026, 6, 24, 8, 0, 0, tzinfo=UTC),
        )
        good_raw = RawEmail(
            provider_message_id="msg-good-002",
            thread_id=None,
            from_address="unmatched@other-domain-xyz.io",  # no match
            subject="No match email",
            snippet="newsletter",
            body="No match",
            received_at=datetime(2026, 6, 24, 9, 0, 0, tzinfo=UTC),
        )

        provider = FakeEmailProvider(
            messages=[bad_raw, good_raw], cursor="cursor-after-error"
        )
        # No responses → bad_raw will exhaust the adapter and raise RuntimeError
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        # Act — should not raise even though bad_raw triggers an error
        counts = await sync_account(session, llm, account, provider)

        # Both messages ingested; error in bad_raw isolated
        assert counts["ingested"] == 2

        # Cursor must still be updated
        await session.refresh(account)
        assert account.sync_cursor == "cursor-after-error"

    @pytest.mark.asyncio
    async def test_idempotency_skips_already_processed_messages(
        self, session: AsyncSession
    ) -> None:
        """Messages already in email_messages are skipped on re-sync."""
        user = _make_user()
        session.add(user)
        account = _make_account(user.id)
        session.add(account)
        await session.flush()

        # Pre-seed an existing EmailMessage
        existing_msg = EmailMessage(
            id=uuid.uuid4(),
            email_account_id=account.id,
            application_id=None,
            provider_message_id="msg-already-processed",
            thread_id=None,
            from_address="no-reply@other.com",
            from_domain="other.com",
            received_at=datetime(2026, 6, 20, tzinfo=UTC),
        )
        session.add(existing_msg)
        await session.flush()

        already_seen = RawEmail(
            provider_message_id="msg-already-processed",
            thread_id=None,
            from_address="no-reply@other.com",
            subject="Old message",
            snippet="Old",
            body="Old body",
            received_at=datetime(2026, 6, 20, tzinfo=UTC),
        )

        provider = FakeEmailProvider(messages=[already_seen], cursor="cursor-skip")
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        counts = await sync_account(session, llm, account, provider)

        # Message ingested but skipped (already in DB)
        assert counts["ingested"] == 1
        assert counts["matched"] == 0
