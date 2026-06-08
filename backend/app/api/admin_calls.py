"""Admin observability endpoints for LLM call logs.

Routes
------
GET  /api/admin/calls              List LlmCall rows with optional filters.
GET  /api/admin/calls/cost         Cost-by-day breakdown and global totals.
GET  /api/admin/calls/{call_id}    Full detail for a single LlmCall.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.repositories.llm_call import LlmCallRepository
from app.schemas.observability import (
    CallTotals,
    CostByDay,
    LlmCallDetail,
    LlmCallRead,
)

router = APIRouter(prefix="/api/admin/calls", tags=["admin", "observability"])


@router.get("", response_model=list[LlmCallRead])
async def list_calls(
    prompt_version_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    model: str | None = Query(default=None),  # noqa: B008
    since: datetime | None = Query(default=None),  # noqa: B008
    until: datetime | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=100, ge=1, le=1000),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[LlmCallRead]:
    """Return LlmCall rows, most-recent first, with optional filters."""
    repo = LlmCallRepository(session)
    calls = await repo.list_calls(
        prompt_version_id=prompt_version_id,
        model=model,
        since=since,
        until=until,
        limit=limit,
    )
    return [LlmCallRead.model_validate(c) for c in calls]


@router.get("/cost", response_model=dict)
async def get_cost_dashboard(
    since: datetime | None = Query(default=None),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:
    """Return cost-per-day breakdown and global aggregate totals."""
    repo = LlmCallRepository(session)
    by_day_rows = await repo.cost_by_day(since=since)
    totals_data = await repo.totals()

    by_day = [
        CostByDay(day=d, cost_usd=float(cost), calls=count)
        for d, cost, count in by_day_rows
    ]
    totals = CallTotals(**totals_data)

    return {"by_day": [item.model_dump() for item in by_day], "totals": totals.model_dump()}


@router.get("/{call_id}", response_model=LlmCallDetail)
async def get_call_detail(
    call_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> LlmCallDetail:
    """Return the full detail for a single LlmCall including rendered_prompt."""
    repo = LlmCallRepository(session)
    call = await repo.get(call_id)
    if call is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LlmCall not found",
        )
    return LlmCallDetail.model_validate(call)
