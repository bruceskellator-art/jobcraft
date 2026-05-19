from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.experience import ExperienceItemRead

ExperienceKind = Literal["work", "project", "education", "skill", "achievement"]


class ExtractedExperience(BaseModel):
    """Single experience item extracted from a resume by the LLM."""

    kind: ExperienceKind
    title: str
    organization: str
    content: str
    start_date: str | None = None
    end_date: str | None = None
    tags: list[str] = Field(default_factory=list)


class ResumeExtractionResult(BaseModel):
    """Top-level structured result returned by the LLM extraction prompt."""

    items: list[ExtractedExperience]


class ResumeImportResponse(BaseModel):
    """Response returned after a successful resume import."""

    created: list[ExperienceItemRead]
