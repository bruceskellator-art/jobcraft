from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.prompt_version import PromptVersion


class PromptVersionRepository:
    """Data-access layer for PromptVersion records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_grouped(self) -> dict[str, list[PromptVersion]]:
        """Return all prompt versions grouped by name, versions in descending order."""
        result = await self._session.execute(
            select(PromptVersion).order_by(PromptVersion.name, PromptVersion.version.desc())
        )
        rows = list(result.scalars().all())

        grouped: dict[str, list[PromptVersion]] = {}
        for pv in rows:
            grouped.setdefault(pv.name, []).append(pv)
        return grouped

    async def get(self, prompt_id: uuid.UUID) -> PromptVersion | None:
        """Return a single PromptVersion by primary key, or None."""
        return await self._session.get(PromptVersion, prompt_id)

    async def list_by_name(self, name: str) -> list[PromptVersion]:
        """Return all versions for the given prompt name, version descending."""
        result = await self._session.execute(
            select(PromptVersion)
            .where(PromptVersion.name == name)
            .order_by(PromptVersion.version.desc())
        )
        return list(result.scalars().all())
