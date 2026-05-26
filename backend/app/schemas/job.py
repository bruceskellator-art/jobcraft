from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.match import MatchRead
from app.scrapers.types import JobFilters


class ExtractedJobView(BaseModel):
    """Subset of extracted job data for UI display. All fields are optional."""

    company: str | None = None
    title: str | None = None
    seniority: str | None = None
    location: str | None = None
    remote_policy: str | None = None
    salary_min_usd: int | None = None
    salary_max_usd: int | None = None
    required_skills: list[str] = []
    preferred_skills: list[str] = []
    summary: str | None = None


class JobPostingRead(BaseModel):
    """Response schema for a persisted job posting."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    source: str
    source_url: str
    source_id: str | None
    company: str
    title: str
    location: str | None
    remote_policy: str | None
    scraped_at: datetime | None
    extracted: dict | None
    match: MatchRead | None = None


class ScrapeRequest(BaseModel):
    """Request body for POST /api/jobs/scrape."""

    filters: JobFilters = JobFilters()
    greenhouse_boards: list[str] = []
    lever_companies: list[str] = []
    extract: bool = False


class ScrapeRunLogView(BaseModel):
    """Per-source run statistics returned in the scrape response."""

    source: str
    total_listed: int
    total_fetched: int
    total_failed: int
    total_new: int


class ScrapeResponse(BaseModel):
    """Response body for POST /api/jobs/scrape."""

    created: int
    runs: list[ScrapeRunLogView]
