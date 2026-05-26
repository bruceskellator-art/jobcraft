from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel


class Gap(BaseModel):
    """A skill gap identified during matching."""

    skill: str
    severity: Literal["low", "mid", "high"]
    rationale: str


class MatchResult(BaseModel):
    """Structured output from the LLM-as-judge scoring stage."""

    overall_score: float
    dimension_scores: dict[str, float]
    gaps: list[Gap]
    rationale: str
    matched_experiences: list[uuid.UUID]
