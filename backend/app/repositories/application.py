"""Data-access layer for Application and ApplicationAttempt records.

Mutating methods flush within the session transaction but do NOT commit.
The caller (router) is responsible for committing at the HTTP-request boundary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.application import Application
from app.db.models.application_attempt import ApplicationAttempt


class ApplicationRepository:
    """CRUD for Application rows.

    Flush-in-repo / commit-in-router pattern.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        user_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> Application:
        """Return existing Application or create one with status='queued'.

        Deduplicates on (user_id, job_id) via a savepoint so that a concurrent
        INSERT that races the initial SELECT is handled gracefully: on
        IntegrityError we roll back the savepoint and re-select the winner row.
        """
        result = await self._session.execute(
            select(Application).where(
                Application.user_id == user_id,
                Application.job_id == job_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        try:
            async with self._session.begin_nested():  # savepoint
                app = Application(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    job_id=job_id,
                    status="queued",
                )
                self._session.add(app)
                await self._session.flush()
                await self._session.refresh(app)
                return app
        except IntegrityError:
            # Another concurrent request inserted the same (user_id, job_id);
            # re-select the existing row.
            result = await self._session.execute(
                select(Application).where(
                    Application.user_id == user_id,
                    Application.job_id == job_id,
                )
            )
            return result.scalar_one()

    async def get(self, application_id: uuid.UUID) -> Application | None:
        """Return an Application by primary key, or None."""
        result = await self._session.execute(
            select(Application).where(Application.id == application_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[Application]:
        """Return all Applications for user_id, optionally filtered by status."""
        stmt = select(Application).where(Application.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Application.status == status)
        stmt = stmt.order_by(Application.updated_at.desc().nullslast(), Application.id.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        app: Application,
        status: str,
        *,
        apply_mode: str | None = None,
        apply_confidence: float | None = None,
        blocked_reason: str | None = None,
        submitted_at: datetime | None = None,
    ) -> Application:
        """Update Application status (and optional fields) via SQL UPDATE.

        Immutable pattern: uses update() rather than mutating in place.
        Flushes and refreshes the instance before returning.
        """
        values: dict[str, Any] = {
            "status": status,
            "updated_at": datetime.now(UTC),
        }
        if apply_mode is not None:
            values["apply_mode"] = apply_mode
        if apply_confidence is not None:
            values["apply_confidence"] = apply_confidence
        if blocked_reason is not None:
            values["blocked_reason"] = blocked_reason
        if submitted_at is not None:
            values["submitted_at"] = submitted_at

        await self._session.execute(
            update(Application).where(Application.id == app.id).values(**values)
        )
        await self._session.flush()
        await self._session.refresh(app)
        return app

    async def count_submitted_today(
        self,
        user_id: uuid.UUID,
    ) -> int:
        """Return total number of submitted applications for user today (all sources).

        Counts rows where submitted_at is today (UTC) and status='submitted',
        across ALL job sources — this is the spec-intended daily total cap.

        NOTE: under concurrent arq workers this COUNT is not lock-protected; a
        distributed lock (Redis INCR or SELECT FOR UPDATE) is required for true
        cap enforcement at scale — TODO for production.
        """
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self._session.execute(
            select(func.count(Application.id))
            .where(
                Application.user_id == user_id,
                Application.status == "submitted",
                Application.submitted_at >= today_start,
            )
        )
        count = result.scalar_one()
        return int(count) if count is not None else 0


class ApplicationAttemptRepository:
    """CRUD for ApplicationAttempt rows.

    Flush-in-repo / commit-in-router pattern.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        application_id: uuid.UUID,
        strategy: str,
        field_map: list | dict,
        overall_confidence: float,
        outcome: str,
        *,
        blocked_reason: str | None = None,
        screenshot_path: str | None = None,
    ) -> ApplicationAttempt:
        """Create a new ApplicationAttempt row and flush."""
        attempt = ApplicationAttempt(
            id=uuid.uuid4(),
            application_id=application_id,
            strategy=strategy,
            field_map=field_map,
            overall_confidence=overall_confidence,
            outcome=outcome,
            blocked_reason=blocked_reason,
            screenshot_path=screenshot_path,
        )
        self._session.add(attempt)
        await self._session.flush()
        await self._session.refresh(attempt)
        return attempt

    async def latest_for(self, application_id: uuid.UUID) -> ApplicationAttempt | None:
        """Return the most-recent ApplicationAttempt for an application, or None."""
        result = await self._session.execute(
            select(ApplicationAttempt)
            .where(ApplicationAttempt.application_id == application_id)
            .order_by(ApplicationAttempt.attempted_at.desc().nullslast())
            .limit(1)
        )
        return result.scalar_one_or_none()
