from __future__ import annotations

from pydantic import BaseModel


class ScrapeProfileConfig(BaseModel):
    """Persisted per-user scrape profile.

    ``query`` is the keyword phrase for LinkedIn + MyCareersFuture; ``companies``
    are curated-registry company names whose Greenhouse/Lever boards are scraped.
    """

    query: str = ""
    companies: list[str] = []
    posted_within_days: int = 30
    extract: bool = False
