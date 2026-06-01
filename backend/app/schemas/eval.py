"""Pydantic v2 schemas for the Eval admin API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AssertionResultView(BaseModel):
    """View of a single assertion result within a case result."""

    kind: str
    passed: bool
    score: float | None = None
    detail: str | None = None


class CaseResultView(BaseModel):
    """View of a single eval case result."""

    case_id: str
    passed: bool
    score: float | None = None
    assertions: list[AssertionResultView] = []


class EvalRunRead(BaseModel):
    """API response schema for an EvalRun record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    suite_name: str
    prompt_version_id: uuid.UUID
    aggregate_scores: dict[str, float]
    results: list[CaseResultView] | list[dict[str, object]]
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RunSuiteRequest(BaseModel):
    """Request body for POST /api/admin/evals/run."""

    suite_name: str
    prompt_version: str | None = None
