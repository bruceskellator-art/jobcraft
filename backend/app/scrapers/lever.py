from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx

from app.scrapers.types import JobFilters, RawJobPosting

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.lever.co/v0/postings"
_RATE_LIMIT_SLEEP = 0.2


class LeverSource:
    """Adapter for the Lever public postings API."""

    name: str

    def __init__(self, company: str, client: httpx.AsyncClient | None = None) -> None:
        self._company = company
        self._client = client or httpx.AsyncClient()
        self.name = f"lever:{company}"

    async def list_jobs(self, filters: JobFilters) -> AsyncIterator[RawJobPosting]:
        url = f"{_BASE_URL}/{self._company}"
        params = {"mode": "json"}
        try:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            postings = resp.json()
        except Exception as exc:
            logger.error("Lever list_jobs failed for %s: %s", self._company, exc)
            return

        cutoff_ts = _cutoff_ts(filters.posted_within_days)

        for raw in postings:
            try:
                posting = _parse_posting(raw, self._company)
            except Exception as exc:
                logger.warning("Lever: failed to parse posting %s: %s", raw.get("id"), exc)
                continue

            if not _passes_filters(posting, filters, raw, cutoff_ts):
                continue

            await asyncio.sleep(_RATE_LIMIT_SLEEP)
            yield posting

    async def fetch_job(self, source_id: str) -> RawJobPosting:
        url = f"{_BASE_URL}/{self._company}/{source_id}"
        resp = await self._client.get(url)
        resp.raise_for_status()
        raw = resp.json()
        return _parse_posting(raw, self._company)


def _cutoff_ts(days: int) -> int:
    """Return a Unix timestamp in milliseconds for `days` ago."""
    dt = datetime.now(tz=UTC) - timedelta(days=days)
    return int(dt.timestamp() * 1000)


def _parse_posting(raw: dict, company: str) -> RawJobPosting:
    posting_id = raw["id"]
    title = raw["text"]
    hosted_url = raw.get("hostedUrl") or f"https://jobs.lever.co/{company}/{posting_id}"
    categories = raw.get("categories") or {}
    location = categories.get("location")
    commitment = categories.get("commitment")  # e.g. "Full-time", "Remote"
    remote_policy = _infer_remote(commitment, location)

    # Prefer plain text; fall back to HTML description
    content = raw.get("descriptionPlain") or raw.get("description") or ""

    return RawJobPosting(
        source=f"lever:{company}",
        source_url=hosted_url,
        source_id=posting_id,
        company=company,
        title=title,
        location=location,
        remote_policy=remote_policy,
        raw_content=content,
    )


def _infer_remote(commitment: str | None, location: str | None) -> str | None:
    combined = f"{commitment or ''} {location or ''}".lower()
    if "remote" in combined:
        return "remote"
    if "hybrid" in combined:
        return "hybrid"
    return None


def _passes_filters(
    posting: RawJobPosting,
    filters: JobFilters,
    raw: dict,
    cutoff_ts: int,
) -> bool:
    # Date filter — Lever uses createdAt in milliseconds
    created_at = raw.get("createdAt")
    if created_at is not None:
        try:
            if int(created_at) < cutoff_ts:
                return False
        except (TypeError, ValueError):
            pass

    # Keyword filter
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
        if posting.remote_policy != "remote":
            content_lower = posting.raw_content.lower()
            title_lower = posting.title.lower()
            if "remote" not in content_lower and "remote" not in title_lower:
                return False

    return True
