from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.llm_call import LlmCall


class LlmCallRepository:
    """Data-access layer for LlmCall records.

    All methods are read-only; LlmCall rows are written by the LLMClient.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_calls(
        self,
        *,
        prompt_version_id: uuid.UUID | None = None,
        model: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[LlmCall]:
        """Return LlmCall rows ordered by called_at descending.

        All filters are optional and composed with AND.
        """
        stmt = select(LlmCall).order_by(LlmCall.called_at.desc()).limit(limit)

        if prompt_version_id is not None:
            stmt = stmt.where(LlmCall.prompt_version_id == prompt_version_id)
        if model is not None:
            stmt = stmt.where(LlmCall.model == model)
        if since is not None:
            stmt = stmt.where(LlmCall.called_at >= since)
        if until is not None:
            stmt = stmt.where(LlmCall.called_at <= until)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, call_id: uuid.UUID) -> LlmCall | None:
        """Return a single LlmCall by primary key, or None."""
        return await self._session.get(LlmCall, call_id)

    async def cost_by_day(
        self,
        *,
        since: datetime | None = None,
    ) -> list[tuple[date, Decimal, int]]:
        """Return (day, total_cost_usd, call_count) grouped by calendar day.

        Rows with NULL cost_usd contribute 0 to the sum via COALESCE.
        Results are ordered oldest-to-newest.
        """
        # Use func.date() for cross-dialect date truncation.
        # SQLite returns a string (YYYY-MM-DD); PostgreSQL returns a date.
        # We normalise to Python date in the result loop below.
        day_col = func.date(LlmCall.called_at).label("day")
        stmt = (
            select(
                day_col,
                func.sum(func.coalesce(LlmCall.cost_usd, 0)).label("total_cost"),
                func.count(LlmCall.id).label("call_count"),
            )
            .group_by(func.date(LlmCall.called_at))
            .order_by(func.date(LlmCall.called_at))
        )

        if since is not None:
            stmt = stmt.where(LlmCall.called_at >= since)

        result = await self._session.execute(stmt)
        rows: list[tuple[date, Decimal, int]] = []
        for row in result.all():
            raw_day = row.day
            # SQLite returns a string; PostgreSQL returns a date object.
            if isinstance(raw_day, str):
                raw_day = date.fromisoformat(raw_day)
            rows.append((raw_day, Decimal(str(row.total_cost)), int(row.call_count)))
        return rows

    async def totals(self) -> dict[str, Any]:
        """Return aggregate metrics across all LlmCall rows.

        Keys: total_cost (Decimal), total_calls (int),
              avg_latency_ms (float | None), error_rate (float).

        NULL cost_usd rows count as 0 cost.
        NULL latency_ms rows are excluded from the average.
        error_rate = rows where error IS NOT NULL / total_calls.
        """
        stmt = select(
            func.count(LlmCall.id).label("total_calls"),
            func.sum(func.coalesce(LlmCall.cost_usd, 0)).label("total_cost"),
            func.avg(LlmCall.latency_ms).label("avg_latency"),
            func.count(LlmCall.error).label("error_count"),
        )

        result = await self._session.execute(stmt)
        row = result.one()

        total_calls = int(row.total_calls or 0)
        total_cost = Decimal(str(row.total_cost or 0))
        avg_latency = float(row.avg_latency) if row.avg_latency is not None else None
        error_count = int(row.error_count or 0)
        error_rate = (error_count / total_calls) if total_calls > 0 else 0.0

        return {
            "total_cost": total_cost,
            "total_calls": total_calls,
            "avg_latency_ms": avg_latency,
            "error_rate": error_rate,
        }
