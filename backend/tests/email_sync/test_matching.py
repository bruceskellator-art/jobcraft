"""Tests for match_message — cheap deterministic → LLM tie-break.

Key assertions:
- Thread match: returns correct app, method='thread', confidence=1.0, LLM NOT called.
- Domain match (single): returns correct app, method='domain', LLM NOT called.
- ATS sender + single open app: method='ats_sender', LLM NOT called.
- LLM tie-break: called ONLY when multiple apps share the same domain.
- Unmatched: returns (None, None, 0.0), LLM NOT called.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.application import Application
from app.db.models.email_message import EmailMessage
from app.db.models.job_posting import JobPosting
from app.email_sync.matching import ATS_SENDER_DOMAINS, match_message
from app.email_sync.provider import RawEmail
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient


def _raw(
    *,
    provider_message_id: str = "msg-001",
    thread_id: str | None = None,
    from_address: str = "recruiter@acmecorp.com",
    subject: str = "Interview invitation",
    snippet: str = "We'd like to invite you",
    received_at: datetime | None = None,
) -> RawEmail:
    return RawEmail(
        provider_message_id=provider_message_id,
        thread_id=thread_id,
        from_address=from_address,
        subject=subject,
        snippet=snippet,
        body="Full body text",
        received_at=received_at or datetime(2026, 6, 24, 9, 0, 0, tzinfo=UTC),
    )


def _app(
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    status: str = "submitted",
    app_id: uuid.UUID | None = None,
) -> Application:
    a = Application(
        id=app_id or uuid.uuid4(),
        user_id=user_id,
        job_id=job_id,
        status=status,
    )
    return a


def _job(company: str = "Acme Corp") -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        source="manual",
        source_url="https://acmecorp.com/jobs/1",
        company=company,
        title="Senior Engineer",
        raw_content="JD content",
    )


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def no_op_llm(session: AsyncSession) -> LLMClient:
    """LLMClient backed by a MockAdapter with no responses — assert it's never called."""
    adapter = MockAdapter(responses=[])
    # Patch pop to raise loudly if called
    return LLMClient(session=session, adapter=adapter)


class TestThreadMatch:
    @pytest.mark.asyncio
    async def test_thread_match_returns_correct_app(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        # Arrange: seed a matching EmailMessage row with the same thread_id
        job = _job()
        session.add(job)
        app = _app(user_id, job.id)
        session.add(app)
        await session.flush()

        existing_msg = EmailMessage(
            id=uuid.uuid4(),
            email_account_id=uuid.uuid4(),
            application_id=app.id,
            provider_message_id="prev-msg-001",
            thread_id="thread-abc",
            from_address="recruiter@acmecorp.com",
            from_domain="acmecorp.com",
            received_at=datetime(2026, 6, 20, tzinfo=UTC),
        )
        session.add(existing_msg)
        await session.flush()

        raw = _raw(thread_id="thread-abc")
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        app_id, method, confidence = await match_message(
            session,
            llm,
            raw,
            open_apps=[app],
            company_domains={app.id: "acmecorp.com"},
        )

        # Assert
        assert app_id == app.id
        assert method == "thread"
        assert confidence == 1.0
        # LLM was NOT called
        assert len(adapter.calls) == 0

    @pytest.mark.asyncio
    async def test_thread_match_takes_priority_over_domain_match(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        # Both thread match AND domain match exist — thread wins (cheapest/most certain)
        job1 = _job("Acme Corp")
        job2 = _job("Acme Corp")
        session.add(job1)
        session.add(job2)
        app1 = _app(user_id, job1.id)
        app2 = _app(user_id, job2.id)
        session.add(app1)
        session.add(app2)
        await session.flush()

        existing_msg = EmailMessage(
            id=uuid.uuid4(),
            email_account_id=uuid.uuid4(),
            application_id=app1.id,
            provider_message_id="prev-thread-msg",
            thread_id="thread-xyz",
            from_address="ats@greenhouse.io",
            from_domain="greenhouse.io",
            received_at=datetime(2026, 6, 20, tzinfo=UTC),
        )
        session.add(existing_msg)
        await session.flush()

        raw = _raw(thread_id="thread-xyz", from_address="ats@greenhouse.io")
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        app_id, method, confidence = await match_message(
            session,
            llm,
            raw,
            open_apps=[app1, app2],
            company_domains={app1.id: "acmecorp.com", app2.id: "acmecorp.com"},
        )

        assert app_id == app1.id
        assert method == "thread"
        assert len(adapter.calls) == 0


class TestDomainMatch:
    @pytest.mark.asyncio
    async def test_single_domain_match_no_llm(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        # Arrange
        job = _job("Acme Corp")
        session.add(job)
        app = _app(user_id, job.id)
        session.add(app)
        await session.flush()

        raw = _raw(from_address="hr@acmecorp.com")
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        app_id, method, confidence = await match_message(
            session,
            llm,
            raw,
            open_apps=[app],
            company_domains={app.id: "acmecorp.com"},
        )

        # Assert
        assert app_id == app.id
        assert method == "domain"
        assert confidence == pytest.approx(0.85)
        assert len(adapter.calls) == 0

    @pytest.mark.asyncio
    async def test_domain_match_is_case_insensitive(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        job = _job("Acme Corp")
        session.add(job)
        app = _app(user_id, job.id)
        session.add(app)
        await session.flush()

        raw = _raw(from_address="HR@ACMECORP.COM")
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        app_id, method, _ = await match_message(
            session,
            llm,
            raw,
            open_apps=[app],
            company_domains={app.id: "acmecorp.com"},
        )

        assert app_id == app.id
        assert method == "domain"
        assert len(adapter.calls) == 0


class TestAtsSenderMatch:
    @pytest.mark.asyncio
    async def test_ats_sender_single_app_no_llm(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        # Arrange: email from known ATS, only one open app
        job = _job("Random Corp")
        session.add(job)
        app = _app(user_id, job.id)
        session.add(app)
        await session.flush()

        raw = _raw(from_address="noreply@greenhouse.io")
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        app_id, method, confidence = await match_message(
            session,
            llm,
            raw,
            open_apps=[app],
            company_domains={app.id: "randomcorp.com"},
        )

        # Assert
        assert app_id == app.id
        assert method == "ats_sender"
        assert confidence == pytest.approx(0.80)
        assert len(adapter.calls) == 0

    @pytest.mark.asyncio
    async def test_ats_sender_multiple_apps_no_match(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        # ATS sender but two open apps and no domain match → unmatched
        job1 = _job("Alpha Corp")
        job2 = _job("Beta Corp")
        session.add(job1)
        session.add(job2)
        app1 = _app(user_id, job1.id)
        app2 = _app(user_id, job2.id)
        session.add(app1)
        session.add(app2)
        await session.flush()

        raw = _raw(from_address="ats@greenhouse.io")
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        app_id, method, confidence = await match_message(
            session,
            llm,
            raw,
            open_apps=[app1, app2],
            company_domains={app1.id: "alphacorp.com", app2.id: "betacorp.com"},
        )

        assert app_id is None
        assert method is None
        assert confidence == 0.0
        assert len(adapter.calls) == 0


class TestLlmTieBreak:
    @pytest.mark.asyncio
    async def test_llm_called_for_multiple_domain_matches(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        # Two open apps at the same company domain → LLM tie-break
        job1 = _job("Acme Corp")
        job2 = _job("Acme Corp")
        session.add(job1)
        session.add(job2)
        app1_id = uuid.uuid4()
        app2_id = uuid.uuid4()
        app1 = _app(user_id, job1.id, app_id=app1_id)
        app2 = _app(user_id, job2.id, app_id=app2_id)
        session.add(app1)
        session.add(app2)
        await session.flush()

        # LLM returns app1's ID
        adapter = MockAdapter(responses=[f'"{app1_id}"'])
        llm = LLMClient(session=session, adapter=adapter)

        raw = _raw(from_address="recruiter@acmecorp.com")
        app_id, method, confidence = await match_message(
            session,
            llm,
            raw,
            open_apps=[app1, app2],
            company_domains={app1_id: "acmecorp.com", app2_id: "acmecorp.com"},
        )

        # Assert LLM WAS called
        assert len(adapter.calls) == 1
        assert app_id == app1_id
        assert method == "llm"

    @pytest.mark.asyncio
    async def test_llm_not_called_for_single_domain_match(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        # Only one domain match → deterministic, LLM NOT called
        job1 = _job("Acme Corp")
        job2 = _job("Beta Corp")
        session.add(job1)
        session.add(job2)
        app1 = _app(user_id, job1.id)
        app2 = _app(user_id, job2.id)
        session.add(app1)
        session.add(app2)
        await session.flush()

        raw = _raw(from_address="recruiter@acmecorp.com")
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        app_id, method, _ = await match_message(
            session,
            llm,
            raw,
            open_apps=[app1, app2],
            company_domains={app1.id: "acmecorp.com", app2.id: "betacorp.com"},
        )

        assert app_id == app1.id
        assert method == "domain"
        assert len(adapter.calls) == 0


class TestUnmatched:
    @pytest.mark.asyncio
    async def test_no_match_returns_none_no_llm(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        job = _job("Other Corp")
        session.add(job)
        app = _app(user_id, job.id)
        session.add(app)
        await session.flush()

        # Sender domain doesn't match any app and is not an ATS sender
        raw = _raw(from_address="spam@newsletter.com")
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        app_id, method, confidence = await match_message(
            session,
            llm,
            raw,
            open_apps=[app],
            company_domains={app.id: "othercorp.com"},
        )

        assert app_id is None
        assert method is None
        assert confidence == 0.0
        assert len(adapter.calls) == 0

    @pytest.mark.asyncio
    async def test_empty_open_apps_returns_none(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        raw = _raw()
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        app_id, method, confidence = await match_message(
            session,
            llm,
            raw,
            open_apps=[],
            company_domains={},
        )

        assert app_id is None
        assert confidence == 0.0
        assert len(adapter.calls) == 0


class TestAtsSenderDomainsContent:
    def test_contains_expected_ats_domains(self) -> None:
        assert "greenhouse.io" in ATS_SENDER_DOMAINS
        assert "lever.co" in ATS_SENDER_DOMAINS
        assert "ashbyhq.com" in ATS_SENDER_DOMAINS
        assert "myworkday.com" in ATS_SENDER_DOMAINS
