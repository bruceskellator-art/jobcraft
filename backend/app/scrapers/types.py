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
    """Per-source accounting for a single scrape run.

    Fields
    ------
    source:
        Identifier of the scrape source (e.g. ``"greenhouse:acme"``).
    total_listed:
        Total items yielded by ``list_jobs`` before any processing.
        Invariant: ``total_listed == total_fetched + total_failed``.
    total_fetched:
        Items successfully obtained (new **and** duplicates).
        ``total_fetched = total_new + (total_listed - total_new - total_failed)``.
    total_new:
        Subset of fetched items that were newly persisted to the database.
    total_failed:
        Items (or source-level errors) that raised a non-fatal exception
        during processing or iteration.
    """

    source: str
    total_listed: int
    total_fetched: int
    total_failed: int
    total_new: int
