"""Tests for field_mapper — safety invariants and resolution paths."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.apply.field_mapper import map_fields
from app.apply.types import KNOCKOUT_KEYS, FormField  # noqa: F401
from app.db.models.job_posting import JobPosting
from app.db.models.user import User
from app.embeddings.fake import FakeEmbeddingAdapter
from app.repositories.answer_bank import AnswerBankRepository
from app.repositories.profile_field import ProfileFieldRepository
from app.services.answer_bank_match import index_approved_answer
from app.vectorstore.memory import InMemoryVectorStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_user(session: AsyncSession) -> User:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", name="Test")
    session.add(user)
    await session.flush()
    return user


def _text_field(name: str, label: str, *, is_knockout: bool = False) -> FormField:
    return FormField(
        name=name,
        label=label,
        field_type="text",
        required=True,
        is_knockout=is_knockout,
    )


def _make_job() -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        source="greenhouse",
        source_url="https://example.com",
        company="Acme",
        title="Engineer",
        raw_content="",
    )


# ---------------------------------------------------------------------------
# Test: knockout field WITH a matching profile value → filled from profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_knockout_field_filled_from_profile(session: AsyncSession) -> None:
    # Arrange
    user = await _make_user(session)
    repo = ProfileFieldRepository(session)
    await repo.upsert(user.id, "work_authorization", "EP holder", is_knockout=True)

    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()

    field = _text_field("work_authorization", "Work Authorization", is_knockout=True)
    job = _make_job()

    # Act
    field_map = await map_fields(session, None, embed, store, user.id, job, [field])

    # Assert
    assert len(field_map.fields) == 1
    mf = field_map.fields[0]
    assert mf.value == "EP holder"
    assert mf.source == "profile"
    assert mf.confidence == 1.0


# ---------------------------------------------------------------------------
# Test: knockout field WITHOUT a profile value → value=None, confidence=0
#        and the LLM is NEVER called to invent a value.
# ---------------------------------------------------------------------------


class _TrackingLLM:
    """Fake LLM that fails the test if called (should never be called for knockout)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def complete(self, *args: object, **kwargs: object) -> object:
        self.calls.append("called")
        raise AssertionError(
            "LLM was called for a knockout field — safety rule violation!"
        )


@pytest.mark.asyncio
async def test_knockout_field_missing_profile_leaves_unfilled(
    session: AsyncSession,
) -> None:
    # Arrange — no profile field for work_authorization
    user = await _make_user(session)
    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()
    tracking_llm = _TrackingLLM()

    field = _text_field("work_authorization", "Work Authorization", is_knockout=True)
    job = _make_job()

    # Act
    field_map = await map_fields(
        session, tracking_llm, embed, store, user.id, job, [field]  # type: ignore[arg-type]
    )

    # Assert — value is None, source "none", confidence 0
    assert len(field_map.fields) == 1
    mf = field_map.fields[0]
    assert mf.value is None
    assert mf.source == "none"
    assert mf.confidence == 0.0

    # Assert — LLM was NOT called (safety invariant)
    assert tracking_llm.calls == [], "LLM must never be called for knockout fields"


# ---------------------------------------------------------------------------
# Test: KNOCKOUT_KEYS trigger knockout logic even without is_knockout=True flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_knockout_key_triggers_profile_only_logic(session: AsyncSession) -> None:
    # Arrange — field named "visa_status" (canonical knockout key)
    user = await _make_user(session)
    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()
    tracking_llm = _TrackingLLM()

    # No profile value for visa_status
    field = _text_field("visa_status", "Visa Status", is_knockout=False)  # flag is False
    job = _make_job()

    field_map = await map_fields(
        session, tracking_llm, embed, store, user.id, job, [field]  # type: ignore[arg-type]
    )

    mf = field_map.fields[0]
    assert mf.value is None
    assert mf.source == "none"
    assert tracking_llm.calls == [], "LLM must not be called for canonical knockout keys"


# ---------------------------------------------------------------------------
# Test: approved answer bank answer is reused for a screening question
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approved_answer_reused_for_screening_question(
    session: AsyncSession,
) -> None:
    # Arrange
    user = await _make_user(session)
    ab_repo = AnswerBankRepository(session)
    answer = await ab_repo.create(
        user.id,
        "What is your notice period?",
        "One month.",
        approved=True,
    )
    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()
    await index_approved_answer(embed, store, answer)

    field = _text_field("notice_period", "What is your notice period?")
    job = _make_job()

    field_map = await map_fields(session, None, embed, store, user.id, job, [field])

    # Assert
    mf = field_map.fields[0]
    assert mf.value == "One month."
    assert mf.source == "answer_bank"
    assert mf.confidence == 0.9


# ---------------------------------------------------------------------------
# Test: unapproved answer is NOT used (approved-only safety rule)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unapproved_answer_not_used(session: AsyncSession) -> None:
    # Arrange — index an answer then revoke approval
    user = await _make_user(session)
    ab_repo = AnswerBankRepository(session)
    answer = await ab_repo.create(
        user.id,
        "What is your notice period?",
        "One month.",
        approved=True,
    )
    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()
    await index_approved_answer(embed, store, answer)
    # Revoke approval
    await ab_repo.set_approved(answer, False)

    field = _text_field("notice_period", "What is your notice period?")
    job = _make_job()

    field_map = await map_fields(session, None, embed, store, user.id, job, [field])

    # Assert — field left unfilled because answer was de-approved
    mf = field_map.fields[0]
    assert mf.value is None
    assert mf.source == "none"
