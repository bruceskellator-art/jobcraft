"""Pydantic v2 schemas for Artifact API responses and generation requests."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class StyleConfigIn(BaseModel):
    """User-facing style configuration mirroring generator.types.StyleConfig."""

    tone: Literal["formal", "balanced", "punchy"] = "balanced"
    length: Literal["one_page", "two_page"] = "one_page"
    emphasis: list[str] = Field(default_factory=list)


class ArtifactScoresView(BaseModel):
    """Read-only view of artifact quality scores."""

    fit: float
    groundedness: float
    ats_keywords: float
    quantified_impact: float
    clarity: float


class ArtifactRead(BaseModel):
    """Response schema for a persisted Artifact record."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID | None
    kind: str
    format: str
    content: str
    is_baseline: bool
    scores: dict | None
    prompt_version_id: uuid.UUID | None
    template_id: str | None
    created_at: datetime | None


class GenerateRequest(BaseModel):
    """Request body for POST /api/jobs/{job_id}/generate."""

    kind: Literal["resume", "cover_letter"]
    style: StyleConfigIn = Field(default_factory=StyleConfigIn)
    template_id: str = "standard"
