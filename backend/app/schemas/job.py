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
    company_logo_url: str | None = None
    title: str
    location: str | None
    remote_policy: str | None
    scraped_at: datetime | None
    extracted: dict | None
    match: MatchRead | None = None


class ScrapeRequest(BaseModel):
    """Request body for scrape endpoints.

    ``query`` drives the keyword sources (LinkedIn + MyCareersFuture);
    ``companies`` are curated-registry company NAMES whose Greenhouse/Lever
    boards are scraped. ``filters.posted_within_days`` carries the lookback.
    """

    query: str = ""
    companies: list[str] = []
    filters: JobFilters = JobFilters()
    extract: bool = False


class JobPostingPage(BaseModel):
    """Paginated envelope for job-posting list responses."""

    items: list[JobPostingRead]
    total: int
    limit: int
    offset: int


class ScrapeRunLogView(BaseModel):
    """Per-source run statistics returned in the scrape response."""

    source: str
    total_listed: int
    total_fetched: int
    total_failed: int
    total_new: int
    error: str | None = None


class ScrapeResponse(BaseModel):
    """Response body for POST /api/jobs/scrape."""

    created: int
    runs: list[ScrapeRunLogView]
