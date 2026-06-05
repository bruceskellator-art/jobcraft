from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.answer_bank import AnswerBank


class AnswerBankRepository:
    """Data-access layer for AnswerBank records.

    Each mutating method flushes changes within the session transaction
    but does NOT commit. The caller (router) is responsible for committing
    or rolling back at the HTTP-request boundary.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: uuid.UUID) -> list[AnswerBank]:
        """Return all answer bank entries for user_id."""
        result = await self._session.execute(
            select(AnswerBank).where(AnswerBank.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get(self, answer_id: uuid.UUID) -> AnswerBank | None:
        """Return a single AnswerBank entry by primary key, or None if absent."""
        return await self._session.get(AnswerBank, answer_id)

    async def create(
        self,
        user_id: uuid.UUID,
        question: str,
        answer: str,
        approved: bool = False,
    ) -> AnswerBank:
        """Persist a new AnswerBank entry and flush to the session.

        Returns the new entry with server-generated defaults populated
        after the flush (id, created_at, updated_at, reuse_count).
        New entries are unapproved by default unless explicitly set.
        """
        entry = AnswerBank(
            user_id=user_id,
            question=question,
            answer=answer,
            approved=approved,
        )
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def set_approved(self, answer: AnswerBank, approved: bool) -> AnswerBank:
        """Set the approved flag via SQL UPDATE (immutable pattern). Returns the updated entry."""
        await self._session.execute(
            update(AnswerBank).where(AnswerBank.id == answer.id).values(approved=approved)
        )
        await self._session.flush()
        await self._session.refresh(answer)
        return answer

    async def increment_reuse(self, answer: AnswerBank) -> AnswerBank:
        """Increment reuse_count by 1 via SQL UPDATE (immutable pattern)."""
        await self._session.execute(
            update(AnswerBank)
            .where(AnswerBank.id == answer.id)
            .values(reuse_count=AnswerBank.reuse_count + 1)
        )
        await self._session.flush()
        await self._session.refresh(answer)
        return answer
