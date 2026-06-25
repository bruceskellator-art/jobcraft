"""Generator domain types: style config, artifact scoring, grounding results, resume data."""

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


# ---------------------------------------------------------------------------
# Structured resume data model (used by template-based generation)
# ---------------------------------------------------------------------------


class ExperienceEntry(BaseModel):
    title: str
    company: str
    location: str | None = None
    start_date: str
    end_date: str
    bullets: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    degree: str
    institution: str
    location: str | None = None
    year: str
    honors: str | None = None
    minor: str | None = None


class ProjectEntry(BaseModel):
    name: str
    role: str | None = None
    organization: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    bullets: list[str] = Field(default_factory=list)


class SkillCategory(BaseModel):
    category: str
    skills: list[str] = Field(default_factory=list)


class ResumeData(BaseModel):
    """Structured resume content used to render HTML/PDF templates.

    All fields sourced strictly from the user's experience items — the LLM
    must not invent facts. The template layer handles all visual presentation;
    this model is presentation-agnostic.
    """

    name: str
    email: str
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None

    summary: str | None = None
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    skills: list[SkillCategory] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
