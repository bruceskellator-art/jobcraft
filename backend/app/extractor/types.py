from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ExtractedJob(BaseModel):
    company: str
    title: str
    seniority: Literal["junior", "mid", "senior", "staff", "principal"] | None
    location: str | None
    remote_policy: Literal["remote", "hybrid", "onsite"] | None
    salary_min_usd: int | None
    salary_max_usd: int | None
    required_skills: list[str]
    preferred_skills: list[str]
    responsibilities: list[str]
    qualifications: list[str]
    culture_signals: list[str]
    summary: str
