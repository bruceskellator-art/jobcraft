from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class LlmCallRead(BaseModel):
    """Lean list-view representation of an LlmCall row.

    Excludes rendered_prompt, inputs, response, and parsed_response to
    keep list payloads small.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prompt_version_id: uuid.UUID
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    cost_usd: float | None
    error: str | None
    called_at: datetime | None

    @field_validator("cost_usd", mode="before")
    @classmethod
    def _coerce_decimal(cls, v: Any) -> float | None:
        """Convert Decimal to float safely; pass through None."""
        if v is None:
            return None
        return float(v)


class LlmCallDetail(LlmCallRead):
    """Full drill-down view of a single LlmCall, including prompt/response."""

    inputs: dict[str, Any]
    rendered_prompt: str
    response: str
    parsed_response: dict[str, Any] | None


class CostByDay(BaseModel):
    """Aggregated cost metrics for a single calendar day."""

    day: date
    cost_usd: float
    calls: int

    @field_validator("cost_usd", mode="before")
    @classmethod
    def _coerce_decimal(cls, v: Any) -> float:
        return float(v)


class CallTotals(BaseModel):
    """Global aggregate metrics across all LlmCall rows."""

    total_cost: float
    total_calls: int
    avg_latency_ms: float | None
    error_rate: float

    @field_validator("total_cost", mode="before")
    @classmethod
    def _coerce_decimal(cls, v: Any) -> float:
        return float(v)


class PromptVersionRead(BaseModel):
    """Lean list-view representation of a PromptVersion row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: int
    model: str
    temperature: float
    is_active: bool
    created_at: datetime | None


class PromptDetail(PromptVersionRead):
    """Full detail view of a PromptVersion including template and metadata."""

    template: str
    metadata_: dict[str, Any] | None
