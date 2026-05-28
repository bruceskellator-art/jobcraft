"""Generator domain types: style config, artifact scoring, and grounding results."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer

# UUID serialized as string so model_dump() produces JSON-safe dicts (SQLite/JSONB).
_UUIDStr = Annotated[
    uuid.UUID,
    PlainSerializer(lambda v: str(v), return_type=str, when_used="always"),
]


class StyleConfig(BaseModel):
    tone: Literal["formal", "balanced", "punchy"] = "balanced"
    length: Literal["one_page", "two_page"] = "one_page"
    emphasis: list[str] = Field(default_factory=list)


class ArtifactScores(BaseModel):
    fit: float
    groundedness: float
    ats_keywords: float
    quantified_impact: float
    clarity: float


class Claim(BaseModel):
    text: str
    experience_id: _UUIDStr | None
    grounded: bool


class GroundednessResult(BaseModel):
    claims: list[Claim]
    grounded_ratio: float
    ungrounded: list[str]


class GeneratedDoc(BaseModel):
    markdown: str
