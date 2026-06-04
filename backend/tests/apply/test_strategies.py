"""Tests for strategy selection and FakeFormSource behaviour."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.apply.browser import FakeFormSource
from app.apply.strategies import (
    GenericFormStrategy,
    GreenhouseFormStrategy,
    select_strategy,
)
from app.apply.types import FormField
from app.db.models.application import Application
from app.db.models.job_posting import JobPosting
from app.db.models.user import User
from app.embeddings.fake import FakeEmbeddingAdapter
from app.vectorstore.memory import InMemoryVectorStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_user(session: AsyncSession) -> User:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", name="Test")
    session.add(user)
    await session.flush()
    return user


def _make_job(source: str) -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        source=source,
        source_url="https://example.com/job",
        company="Acme",
        title="Software Engineer",
        raw_content="",
    )


def _make_app(user_id: uuid.UUID, job_id: uuid.UUID) -> Application:
    return Application(
        id=uuid.uuid4(),
        user_id=user_id,
        job_id=job_id,
        status="queued",
    )


def _simple_fields() -> list[FormField]:
    return [
        FormField(name="email", label="Email Address", field_type="email", required=True),
        FormField(name="name", label="Full Name", field_type="text", required=True),
    ]


# ---------------------------------------------------------------------------
# Strategy selection
# ---------------------------------------------------------------------------


def test_select_strategy_picks_greenhouse_for_greenhouse_job() -> None:
    greenhouse_job = _make_job("greenhouse")
    fake_source = FakeFormSource(_simple_fields())

    strategies = [
        GreenhouseFormStrategy(fake_source),  # type: ignore[arg-type]
        GenericFormStrategy(fake_source),  # type: ignore[arg-type]
    ]
    chosen = select_strategy(greenhouse_job, strategies)  # type: ignore[arg-type]
    assert isinstance(chosen, GreenhouseFormStrategy)
    assert chosen.name == "greenhouse"


def test_select_strategy_falls_back_to_generic_for_unknown_source() -> None:
    lever_job = _make_job("lever")
    fake_source = FakeFormSource(_simple_fields())

    strategies = [
        GreenhouseFormStrategy(fake_source),  # type: ignore[arg-type]
        GenericFormStrategy(fake_source),  # type: ignore[arg-type]
    ]
    chosen = select_strategy(lever_job, strategies)  # type: ignore[arg-type]
    assert isinstance(chosen, GenericFormStrategy)
    assert chosen.name == "generic"


def test_select_strategy_raises_when_no_strategy_matches() -> None:
    job = _make_job("workday")
    # Only greenhouse strategy — no fallback
    strategies = [GreenhouseFormStrategy(FakeFormSource(_simple_fields()))]  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="No strategy"):
        select_strategy(job, strategies)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# FakeFormSource: captcha → blocked outcome
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_form_source_captcha_returns_blocked(session: AsyncSession) -> None:
    user = await _make_user(session)
    job = _make_job("some_board")
    session.add(job)
    await session.flush()
    app = _make_app(user.id, job.id)
    session.add(app)
    await session.flush()

    fake_source = FakeFormSource(_simple_fields(), captcha=True)
    strategy = GenericFormStrategy(fake_source)  # type: ignore[arg-type]

    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()

    # Fill fields first
    field_map = await strategy.fill(app, job, session, None, embed, store, user.id)

    # Submit — should be blocked due to captcha
    outcome = await strategy.submit(job, field_map)
    assert outcome.outcome == "blocked"
    assert outcome.blocked_reason is not None
    assert "captcha" in outcome.blocked_reason.lower()


@pytest.mark.asyncio
async def test_fake_form_source_no_captcha_returns_submitted(session: AsyncSession) -> None:
    user = await _make_user(session)
    job = _make_job("some_board")
    session.add(job)
    await session.flush()
    app = _make_app(user.id, job.id)
    session.add(app)
    await session.flush()

    fake_source = FakeFormSource(_simple_fields(), captcha=False)
    strategy = GenericFormStrategy(fake_source)  # type: ignore[arg-type]

    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()

    field_map = await strategy.fill(app, job, session, None, embed, store, user.id)
    outcome = await strategy.submit(job, field_map)
    assert outcome.outcome == "submitted"
    # FakeFormSource records the submission
    assert len(fake_source.submitted_field_maps) == 1
