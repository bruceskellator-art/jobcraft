"""Repository-layer tests for ProfileFieldRepository and AnswerBankRepository."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.repositories.answer_bank import AnswerBankRepository
from app.repositories.profile_field import ProfileFieldRepository


async def _make_user(session: AsyncSession) -> User:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", name="Test User")
    session.add(user)
    await session.flush()
    return user


class TestProfileFieldRepository:
    """Unit tests for ProfileFieldRepository."""

    async def test_upsert_inserts_new_field(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        repo = ProfileFieldRepository(session)

        # Act
        field = await repo.upsert(user.id, "location", "Singapore", False)

        # Assert
        assert field.id is not None
        assert field.key == "location"
        assert field.value == "Singapore"
        assert field.is_knockout is False

    async def test_upsert_updates_existing_field_by_same_key(
        self, session: AsyncSession
    ) -> None:
        # Arrange
        user = await _make_user(session)
        repo = ProfileFieldRepository(session)
        first = await repo.upsert(user.id, "location", "Singapore", False)

        # Act — same key, different value
        second = await repo.upsert(user.id, "location", "Kuala Lumpur", True)

        # Assert — same id (update, not insert)
        assert second.id == first.id
        assert second.value == "Kuala Lumpur"
        assert second.is_knockout is True

    async def test_upsert_different_keys_creates_separate_rows(
        self, session: AsyncSession
    ) -> None:
        # Arrange
        user = await _make_user(session)
        repo = ProfileFieldRepository(session)

        # Act
        f1 = await repo.upsert(user.id, "location", "Singapore", False)
        f2 = await repo.upsert(user.id, "salary", "120000", True)

        # Assert
        assert f1.id != f2.id

    async def test_list_by_user_returns_all_fields(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        repo = ProfileFieldRepository(session)
        await repo.upsert(user.id, "location", "Singapore", False)
        await repo.upsert(user.id, "salary", "120000", True)

        # Act
        fields = await repo.list_by_user(user.id)

        # Assert
        assert len(fields) == 2

    async def test_list_by_user_does_not_leak_other_users(
        self, session: AsyncSession
    ) -> None:
        # Arrange
        user_a = await _make_user(session)
        user_b = await _make_user(session)
        repo = ProfileFieldRepository(session)
        await repo.upsert(user_a.id, "location", "Singapore", False)

        # Act
        fields_b = await repo.list_by_user(user_b.id)

        # Assert
        assert fields_b == []

    async def test_get_by_key_returns_field(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        repo = ProfileFieldRepository(session)
        await repo.upsert(user.id, "location", "Singapore", False)

        # Act
        field = await repo.get_by_key(user.id, "location")

        # Assert
        assert field is not None
        assert field.value == "Singapore"

    async def test_get_by_key_returns_none_for_missing(
        self, session: AsyncSession
    ) -> None:
        # Arrange
        user = await _make_user(session)
        repo = ProfileFieldRepository(session)

        # Act
        field = await repo.get_by_key(user.id, "nonexistent")

        # Assert
        assert field is None

    async def test_delete_removes_field(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        repo = ProfileFieldRepository(session)
        field = await repo.upsert(user.id, "location", "Singapore", False)

        # Act
        await repo.delete(field)

        # Assert
        result = await repo.get_by_key(user.id, "location")
        assert result is None


class TestAnswerBankRepository:
    """Unit tests for AnswerBankRepository."""

    async def test_create_sets_defaults(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        repo = AnswerBankRepository(session)

        # Act
        entry = await repo.create(user.id, "What is your notice period?", "One month.")

        # Assert
        assert entry.id is not None
        assert entry.approved is False
        assert entry.reuse_count == 0

    async def test_create_with_approved_true(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        repo = AnswerBankRepository(session)

        # Act
        entry = await repo.create(
            user.id, "Tell me about yourself.", "Experienced engineer.", approved=True
        )

        # Assert
        assert entry.approved is True

    async def test_set_approved_true(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        repo = AnswerBankRepository(session)
        entry = await repo.create(user.id, "Q?", "A.")

        # Act
        updated = await repo.set_approved(entry, True)

        # Assert
        assert updated.approved is True

    async def test_set_approved_false(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        repo = AnswerBankRepository(session)
        entry = await repo.create(user.id, "Q?", "A.", approved=True)

        # Act
        updated = await repo.set_approved(entry, False)

        # Assert
        assert updated.approved is False

    async def test_increment_reuse_increases_count(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        repo = AnswerBankRepository(session)
        entry = await repo.create(user.id, "Q?", "A.")

        # Act
        updated = await repo.increment_reuse(entry)

        # Assert
        assert updated.reuse_count == 1

    async def test_increment_reuse_twice(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        repo = AnswerBankRepository(session)
        entry = await repo.create(user.id, "Q?", "A.")

        # Act
        entry = await repo.increment_reuse(entry)
        entry = await repo.increment_reuse(entry)

        # Assert
        assert entry.reuse_count == 2

    async def test_list_by_user_returns_created_entries(
        self, session: AsyncSession
    ) -> None:
        # Arrange
        user = await _make_user(session)
        repo = AnswerBankRepository(session)
        await repo.create(user.id, "Q1?", "A1.")
        await repo.create(user.id, "Q2?", "A2.")

        # Act
        entries = await repo.list_by_user(user.id)

        # Assert
        assert len(entries) == 2

    async def test_get_returns_entry_by_id(self, session: AsyncSession) -> None:
        # Arrange
        user = await _make_user(session)
        repo = AnswerBankRepository(session)
        entry = await repo.create(user.id, "Q?", "A.")

        # Act
        fetched = await repo.get(entry.id)

        # Assert
        assert fetched is not None
        assert fetched.id == entry.id

    async def test_get_returns_none_for_missing(self, session: AsyncSession) -> None:
        # Arrange
        repo = AnswerBankRepository(session)

        # Act
        result = await repo.get(uuid.uuid4())

        # Assert
        assert result is None
