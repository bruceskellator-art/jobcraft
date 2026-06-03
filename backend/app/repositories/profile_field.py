from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.profile_field import ProfileField


class ProfileFieldRepository:
    """Data-access layer for ProfileField records.

    Each mutating method flushes changes within the session transaction
    but does NOT commit. The caller (router) is responsible for committing
    or rolling back at the HTTP-request boundary.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: uuid.UUID) -> list[ProfileField]:
        """Return all profile fields for user_id."""
        result = await self._session.execute(
            select(ProfileField).where(ProfileField.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_by_key(self, user_id: uuid.UUID, key: str) -> ProfileField | None:
        """Return a single ProfileField by (user_id, key), or None if absent."""
        result = await self._session.execute(
            select(ProfileField).where(
                ProfileField.user_id == user_id,
                ProfileField.key == key,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: uuid.UUID,
        key: str,
        value: str,
        is_knockout: bool,
    ) -> ProfileField:
        """Insert a new field or update the existing row matching (user_id, key).

        Returns the persisted ProfileField after flushing. The UNIQUE constraint
        on (user_id, key) guarantees at most one row per key per user.
        """
        existing = await self.get_by_key(user_id, key)
        if existing is not None:
            existing.value = value
            existing.is_knockout = is_knockout
            self._session.add(existing)
            await self._session.flush()
            await self._session.refresh(existing)
            return existing

        field = ProfileField(user_id=user_id, key=key, value=value, is_knockout=is_knockout)
        self._session.add(field)
        await self._session.flush()
        await self._session.refresh(field)
        return field

    async def delete(self, field: ProfileField) -> None:
        """Delete field and flush the deletion to the session."""
        await self._session.delete(field)
        await self._session.flush()
