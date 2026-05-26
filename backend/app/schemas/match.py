"""Response schemas for the match API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class GapView(BaseModel):
    """A single skill gap, as surfaced in the match response."""

    skill: str
    severity: str
    rationale: str


class MatchRead(BaseModel):
    """Response schema for a persisted Match record."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    overall_score: float
    dimension_scores: dict[str, float]
    gaps: list[Any]
    rationale: str
    computed_at: datetime | None
