"""Service-layer tests for answer_bank_match — approved-only safety rule."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.embeddings.fake import FakeEmbeddingAdapter
from app.repositories.answer_bank import AnswerBankRepository
from app.services.answer_bank_match import find_similar_answer, index_approved_answer
from app.vectorstore.memory import InMemoryVectorStore


async def _make_user(session: AsyncSession) -> User:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", name="Test")
    session.add(user)
    await session.flush()
    return user


class TestIndexApprovedAnswer:
    async def test_index_upserts_point_into_store(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        repo = AnswerBankRepository(session)
        answer = await repo.create(
            user.id, "What is your notice period?", "One month.", approved=True
        )
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()

        # Act
        await index_approved_answer(embed, store, answer)

        # Assert — collection exists and has one point
        query_vec = (await embed.embed(["notice period"]))[0]
        results = await store.search("answer_bank", query_vec, top_k=5)
        assert len(results) >= 1
        assert any(r.payload.get("answer_id") == str(answer.id) for r in results)


class TestFindSimilarAnswer:
    async def test_returns_approved_answer_above_threshold(
        self, session: AsyncSession
    ) -> None:
        # Arrange
        user = await _make_user(session)
        repo = AnswerBankRepository(session)
        answer = await repo.create(
            user.id,
            "What is your notice period?",
            "One month.",
            approved=True,
        )
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        await index_approved_answer(embed, store, answer)

        # Act — identical question should score 1.0 (above any threshold)
        result = await find_similar_answer(
            session, embed, store, user.id, "What is your notice period?", threshold=0.85
        )

        # Assert
        assert result is not None
        assert result.id == answer.id

    async def test_unapproved_answer_never_returned(
        self, session: AsyncSession
    ) -> None:
        # Arrange — create entry, index manually but do NOT approve it in DB
        user = await _make_user(session)
        repo = AnswerBankRepository(session)
        # Create as approved=True so we can index it, then revoke approval
        answer = await repo.create(
            user.id,
            "What is your notice period?",
            "One month.",
            approved=True,
        )
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        # Index while approved
        await index_approved_answer(embed, store, answer)
        # Revoke approval in DB (simulates de-approval after indexing)
        await repo.set_approved(answer, False)

        # Act — vector is still in store but DB row is unapproved
        result = await find_similar_answer(
            session, embed, store, user.id, "What is your notice period?", threshold=0.85
        )

        # Assert — safety rule: must return None
        assert result is None

    async def test_below_threshold_returns_none(self, session: AsyncSession) -> None:
        # Arrange — index an approved answer with a question about "notice period"
        user = await _make_user(session)
        repo = AnswerBankRepository(session)
        answer = await repo.create(
            user.id,
            "What is your notice period?",
            "One month.",
            approved=True,
        )
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        await index_approved_answer(embed, store, answer)

        # Act — use a threshold of 1.01 (impossible to meet) to force None
        result = await find_similar_answer(
            session, embed, store, user.id, "What is your notice period?", threshold=1.01
        )

        # Assert
        assert result is None

    async def test_returns_none_when_store_empty(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()

        # Act — nothing indexed
        result = await find_similar_answer(
            session, embed, store, user.id, "Any question?", threshold=0.85
        )

        # Assert
        assert result is None

    async def test_does_not_return_other_users_answers(
        self, session: AsyncSession
    ) -> None:
        # Arrange — index answer for user_a, search as user_b
        user_a = await _make_user(session)
        user_b = await _make_user(session)
        repo = AnswerBankRepository(session)
        answer = await repo.create(
            user_a.id,
            "What is your notice period?",
            "One month.",
            approved=True,
        )
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        await index_approved_answer(embed, store, answer)

        # Act — user_b searches for same question
        result = await find_similar_answer(
            session, embed, store, user_b.id, "What is your notice period?", threshold=0.85
        )

        # Assert — user_b gets nothing (payload filter on user_id)
        assert result is None
