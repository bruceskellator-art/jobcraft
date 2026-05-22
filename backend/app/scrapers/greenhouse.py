from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx

from app.scrapers.types import JobFilters, RawJobPosting

logger = logging.getLogger(__name__)

_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
_RATE_LIMIT_SLEEP = 0.2  # seconds between requests


class GreenhouseSource:
    """Adapter for the Greenhouse public job board JSON API."""

    name: str

    def __init__(self, board_token: str, client: httpx.AsyncClient | None = None) -> None:
        self._board_token = board_token
        self._client = client or httpx.AsyncClient()
        self.name = f"greenhouse:{board_token}"

    async def list_jobs(self, filters: JobFilters) -> AsyncIterator[RawJobPosting]:
        url = f"{_BASE_URL}/{self._board_token}/jobs"
        params = {"content": "true"}
        try:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("Greenhouse list_jobs failed for %s: %s", self._board_token, exc)
            return

        jobs = data.get("jobs", [])
        cutoff = _cutoff_dt(filters.posted_within_days)

        for raw in jobs:
            try:
                posting = _parse_posting(raw, self._board_token)
            except Exception as exc:
                logger.warning("Greenhouse: failed to parse posting %s: %s", raw.get("id"), exc)
                continue

            if not _passes_filters(posting, filters, raw, cutoff):
                continue

            await asyncio.sleep(_RATE_LIMIT_SLEEP)
            yield posting

    async def fetch_job(self, source_id: str) -> RawJobPosting:
        url = f"{_BASE_URL}/{self._board_token}/jobs/{source_id}"
        resp = await self._client.get(url)
        resp.raise_for_status()
        raw = resp.json()
        return _parse_posting(raw, self._board_token)


def _cutoff_dt(days: int) -> datetime:
    return datetime.now(tz=UTC) - timedelta(days=days)


def _parse_posting(raw: dict, board_token: str) -> RawJobPosting:
    """Parse a Greenhouse API job dict into RawJobPosting. Raises on missing required fields."""
    job_id = str(raw["id"])
    title = raw["title"]
    absolute_url = (
        raw.get("absolute_url")
        or f"https://boards.greenhouse.io/{board_token}/jobs/{job_id}"
    )
    location = (raw.get("location") or {}).get("name")
    content = raw.get("content") or ""
    # Use board_token as company — no per-job company field in Greenhouse public API
    company = board_token

    return RawJobPosting(
        source=f"greenhouse:{board_token}",
        source_url=absolute_url,
        source_id=job_id,
        company=company,
        title=title,
        location=location,
        remote_policy=None,
        raw_content=content,
    )


def _passes_filters(
    posting: RawJobPosting,
    filters: JobFilters,
    raw: dict,
    cutoff: datetime,
) -> bool:
    # Date filter
    updated_at_str = raw.get("updated_at")
    if updated_at_str:
        try:
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            if updated_at < cutoff:
                return False
        except ValueError:
            pass  # unparseable date — let it through

    # Keyword filter (title + raw_content)
    if filters.keywords:
        haystack = f"{posting.title} {posting.raw_content}".lower()
        if not any(kw.lower() in haystack for kw in filters.keywords):
            return False

    # Company filter
    if filters.companies:
        if not any(c.lower() in posting.company.lower() for c in filters.companies):
            return False

    # remote_only filter
    if filters.remote_only:
        content_lower = posting.raw_content.lower()
        title_lower = posting.title.lower()
        if "remote" not in content_lower and "remote" not in title_lower:
            return False

    return True
