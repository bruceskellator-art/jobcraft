from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


class JobFilters(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    companies: list[str] | None = None
    locations: list[str] | None = None
    remote_only: bool = False
    seniority: list[Literal["junior", "mid", "senior", "staff"]] | None = None
    posted_within_days: int = 30


@dataclass(frozen=True)
class RawJobPosting:
    source: str
    source_url: str
    source_id: str | None
    company: str
    title: str
    location: str | None
    remote_policy: str | None
    raw_content: str


@dataclass(frozen=True)
class ScrapeRunLog:
    """Per-source accounting for a single scrape run."""

    source: str
    total_listed: int
    total_fetched: int
    total_failed: int
    total_new: int
    error: str | None = None
