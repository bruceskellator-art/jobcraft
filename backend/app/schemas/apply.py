"""Pydantic schemas for the Apply API (Phase 6, §4.8)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ApplicationRead(BaseModel):
    """Public representation of an Application row."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    job_id: uuid.UUID
    status: str
    apply_mode: str | None = None
    apply_confidence: float | None = None
    blocked_reason: str | None = None
    submitted_at: datetime | None = None
    updated_at: datetime | None = None


class MappedFieldView(BaseModel):
    """View of a single mapped form field (subset of MappedField)."""

    name: str
    label: str
    value: str | None
    source: str
    confidence: float


class FieldMapView(BaseModel):
    """View of a FieldMap's resolved fields and aggregate confidence."""

    fields: list[MappedFieldView]
    overall_confidence: float


class JobSummary(BaseModel):
    """Minimal job info embedded in queue items."""

    id: uuid.UUID
    title: str
    company: str
    source: str


class ApplyQueueItem(BaseModel):
    """An application pending manual review, with its latest field map."""

    application: ApplicationRead
    job: JobSummary
    field_map: FieldMapView | None = None


class ApplicationAttemptRead(BaseModel):
    """Public representation of an ApplicationAttempt row."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    application_id: uuid.UUID
    strategy: str
    field_map: Any  # raw JSONB stored as list/dict
    overall_confidence: float
    outcome: str
    blocked_reason: str | None = None
    screenshot_path: str | None = None
    attempted_at: datetime | None = None


class EnqueueRequest(BaseModel):
    """Request body for POST /api/apply/queue."""

    job_ids: list[uuid.UUID] = Field(..., min_length=1)


class RunQueueRequest(BaseModel):
    """Request body for POST /api/applications/{id}/process."""

    limit: int = Field(default=50, ge=1)
    dry_run: bool = True


class StatusUpdateRequest(BaseModel):
    """Request body for PATCH /api/applications/{id}/status."""

    status: str
