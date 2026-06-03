from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Profile field schemas
# ---------------------------------------------------------------------------


class ProfileFieldRead(BaseModel):
    """Schema for reading a profile field."""

    id: uuid.UUID
    key: str
    value: str
    is_knockout: bool

    model_config = {"from_attributes": True}


class ProfileFieldUpsert(BaseModel):
    """Schema for creating or updating a profile field."""

    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    is_knockout: bool = False


# ---------------------------------------------------------------------------
# Answer bank schemas
# ---------------------------------------------------------------------------


class AnswerBankRead(BaseModel):
    """Schema for reading an answer bank entry."""

    id: uuid.UUID
    question: str
    answer: str
    approved: bool
    reuse_count: int

    model_config = {"from_attributes": True}


class AnswerBankCreate(BaseModel):
    """Schema for creating a new answer bank entry (draft, unapproved)."""

    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class AnswerBankApprove(BaseModel):
    """Schema for setting the approved flag on an answer bank entry."""

    approved: bool


# ---------------------------------------------------------------------------
# Autopilot config schema (mirrors AutopilotConfig from services/autopilot.py)
# ---------------------------------------------------------------------------


class AutopilotConfigIO(BaseModel):
    """I/O schema for autopilot configuration, mirrors AutopilotConfig exactly."""

    mode: str = "selective"
    auto_submit_sources: list[str] = Field(
        default_factory=lambda: ["linkedin_easy_apply", "mycareersfuture"]
    )
    min_confidence: float = 0.75
    min_fit: float = 0.55
    daily_cap: int = 80
