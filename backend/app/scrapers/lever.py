from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Self

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.scrapers.types import JobFilters, RawJobPosting

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.lever.co/v0/postings"
_RATE_LIMIT_SLEEP = 0.2  # seconds between HTTP requests


def _is_retryable(exc: BaseException) -> bool:
    """True for transient HTTP errors, timeouts, and 5xx responses."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


_retry = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10),
    reraise=True,
)


class LeverSource:
    """Adapter for the Lever public postings API.

    Lifetime management
    -------------------
    When no *client* is injected, the adapter creates its own ``httpx.AsyncClient``
    and takes ownership of it.  Owned clients are closed on ``aclose()``.
    Injected clients are never closed by this class.

    Use as an async context manager to guarantee cleanup::

        async with LeverSource(company) as src:
            async for posting in src.list_jobs(filters):
                ...
    """

    name: str

    def __init__(self, company: str, client: httpx.AsyncClient | None = None) -> None:
        self._company = company
        if client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
            )
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False
        self.name = f"lever:{company}"

    async def aclose(self) -> None:
        """Close the underlying HTTP client if this adapter created it."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def list_jobs(
        self,
        filters: JobFilters,
        *,
        now: datetime | None = None,
    ) -> AsyncIterator[RawJobPosting]:
        url = f"{_BASE_URL}/{self._company}"
        params = {"mode": "json"}
        try:
            resp = await _retry(self._client.get)(url, params=params)
            await asyncio.sleep(_RATE_LIMIT_SLEEP)
            resp.raise_for_status()
            postings = resp.json()
        except Exception as exc:
            logger.error("Lever list_jobs failed for %s: %s", self._company, exc)
            return

        cutoff_ts = _cutoff_ts(filters.posted_within_days, now=now)

        for raw in postings:
            try:
                posting = _parse_posting(raw, self._company)
            except Exception as exc:
                logger.warning("Lever: failed to parse posting %s: %s", raw.get("id"), exc)
                continue

            if not _passes_filters(posting, filters, raw, cutoff_ts):
                continue

            yield posting

    async def fetch_job(self, source_id: str) -> RawJobPosting:
        url = f"{_BASE_URL}/{self._company}/{source_id}"
        resp = await _retry(self._client.get)(url)
        await asyncio.sleep(_RATE_LIMIT_SLEEP)
        resp.raise_for_status()
        raw = resp.json()
        return _parse_posting(raw, self._company)


def _cutoff_ts(days: int, *, now: datetime | None = None) -> int:
    """Return a Unix timestamp in milliseconds for *days* ago from *now*."""
    reference = now if now is not None else datetime.now(tz=UTC)
    dt = reference - timedelta(days=days)
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
