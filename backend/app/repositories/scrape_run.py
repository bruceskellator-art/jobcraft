from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.scrape_run import ScrapeRun


class ScrapeRunRepository:
    """Data-access layer for ScrapeRun records.

    Mutating methods flush within the session transaction but do NOT commit.
    The caller (route or background runner) is responsible for committing.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: uuid.UUID, request: dict) -> ScrapeRun:
        """Create a new run in the ``pending`` state."""
        run = ScrapeRun(user_id=user_id, status="pending", request=request)
        self._session.add(run)
        await self._session.flush()
        await self._session.refresh(run)
        return run

    async def get(self, run_id: uuid.UUID) -> ScrapeRun | None:
        """Return a run by id, or None."""
        return await self._session.get(ScrapeRun, run_id)

    async def list_recent(
        self, user_id: uuid.UUID, *, limit: int = 20
    ) -> list[ScrapeRun]:
        """Return the user's most recent runs, newest first."""
        result = await self._session.execute(
            select(ScrapeRun)
            .where(ScrapeRun.user_id == user_id)
            .order_by(ScrapeRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_running(self, run_id: uuid.UUID) -> None:
        """Transition a run to ``running`` and stamp started_at."""
        from sqlalchemy import func, update

        await self._session.execute(
            update(ScrapeRun)
            .where(ScrapeRun.id == run_id)
            .values(status="running", started_at=func.now())
        )
        await self._session.flush()

    async def mark_finished(
        self,
        run_id: uuid.UUID,
        *,
        status: str,
        total_created: int = 0,
        runs: list | None = None,
        error: str | None = None,
    ) -> None:
        """Finalize a run with its outcome and stamp finished_at."""
        from sqlalchemy import func, update

        await self._session.execute(
            update(ScrapeRun)
            .where(ScrapeRun.id == run_id)
            .values(
                status=status,
                total_created=total_created,
                runs=runs,
                error=error,
                finished_at=func.now(),
            )
        )
        await self._session.flush()
