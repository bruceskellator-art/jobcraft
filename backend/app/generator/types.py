"""Generator domain types: style config, artifact scoring, and grounding results."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer, model_validator

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
    grounded_ratio: float = Field(ge=0.0, le=1.0)
    ungrounded: list[str]

    @model_validator(mode="after")
    def _recompute_from_claims(self) -> GroundednessResult:
        """Recompute grounded_ratio and ungrounded from claims.

        Never trust the LLM's verbatim values — derive them from the
        structured claim objects so they are always internally consistent.
        Empty claims list → grounded_ratio = 0.0 (not 1.0).
        """
        if not self.claims:
            self.grounded_ratio = 0.0
            self.ungrounded = []
            return self
        grounded_count = sum(1 for c in self.claims if c.grounded)
        self.grounded_ratio = grounded_count / len(self.claims)
        self.ungrounded = [c.text for c in self.claims if not c.grounded]
        return self


class GeneratedDoc(BaseModel):
    markdown: str
