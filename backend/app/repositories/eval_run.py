"""Repository for EvalRun records."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.eval_run import EvalRun


class EvalRunRepository:
    """Data-access layer for EvalRun records.

    Read-only: the runner owns persistence; this repo only queries.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, *, limit: int = 100) -> list[EvalRun]:
        """Return the most-recent EvalRun records, ordered by started_at desc.

        Falls back to completed_at desc for records without started_at.
        """
        stmt = (
            select(EvalRun)
            .order_by(EvalRun.started_at.desc().nulls_last())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, run_id: uuid.UUID) -> EvalRun | None:
        """Return a single EvalRun by primary key, or None if not found."""
        return await self._session.get(EvalRun, run_id)
