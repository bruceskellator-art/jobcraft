from __future__ import annotations

from pydantic import BaseModel


class ScrapeProfileConfig(BaseModel):
    """Persisted per-user scrape profile.

    ``query`` is the keyword phrase for LinkedIn + MyCareersFuture; ``companies``
    are curated-registry company names whose Greenhouse/Lever boards are scraped.
    ``location`` is a free-text location hint passed as ``filters.locations`` when
    triggering a scrape from the saved profile.
    """

    query: str = ""
    companies: list[str] = []
    location: str = ""
    posted_within_days: int = 30
    extract: bool = False
