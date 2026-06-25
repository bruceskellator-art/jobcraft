from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.experience_item import ExperienceItem
from app.schemas.experience import ExperienceItemCreate, ExperienceItemUpdate


class ExperienceRepository:
    """Data-access layer for ExperienceItem records.

    Each mutating method flushes changes to the database within the
    session transaction but does NOT commit. The caller (router) is
    responsible for committing or rolling back. This keeps the
    transaction boundary at the HTTP-request level and makes the
    repository easy to compose in tests.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: uuid.UUID) -> list[ExperienceItem]:
        """Return all experience items belonging to user_id, sorted by sort_order then created_at."""
        result = await self._session.execute(
            select(ExperienceItem)
            .where(ExperienceItem.user_id == user_id)
            .order_by(
                ExperienceItem.sort_order.asc().nulls_last(),
                ExperienceItem.created_at.asc(),
            )
        )
        return list(result.scalars().all())

    async def reorder_kind(
        self, user_id: uuid.UUID, kind: str, ordered_ids: list[uuid.UUID]
    ) -> None:
        """Assign sort_order values to items of a given kind based on ordered_ids position."""
        for position, item_id in enumerate(ordered_ids):
            item = await self._session.get(ExperienceItem, item_id)
            if item is None or item.user_id != user_id or item.kind != kind:
                continue
            item.sort_order = position
            self._session.add(item)
        await self._session.flush()

    async def get(self, item_id: uuid.UUID) -> ExperienceItem | None:
        """Return a single item by primary key, or None if not found."""
        return await self._session.get(ExperienceItem, item_id)

    async def create(
        self, user_id: uuid.UUID, data: ExperienceItemCreate
    ) -> ExperienceItem:
        """Persist a new ExperienceItem and flush to the session.

        Returns the new item with server-generated defaults populated
        after the flush (id, created_at, updated_at).
        """
        raw = data.model_dump(by_alias=False, exclude_unset=False)
        item = ExperienceItem(user_id=user_id, **raw)
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def update(
        self, item: ExperienceItem, data: ExperienceItemUpdate
    ) -> ExperienceItem:
        """Apply only the fields that were explicitly set in data.

        Builds a new state dict without mutating the Pydantic schema
        object, then writes each field onto the ORM instance.
        Returns the updated item after flushing.
        """
        updates = data.model_dump(by_alias=False, exclude_unset=True)
        for field, value in updates.items():
            setattr(item, field, value)
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def delete(self, item: ExperienceItem) -> None:
        """Delete item and flush the deletion to the session."""
        await self._session.delete(item)
        await self._session.flush()
