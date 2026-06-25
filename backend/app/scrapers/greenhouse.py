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

_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
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


class GreenhouseSource:
    """Adapter for the Greenhouse public job board JSON API.

    Lifetime management
    -------------------
    When no *client* is injected, the adapter creates its own ``httpx.AsyncClient``
    and takes ownership of it.  Owned clients are closed on ``aclose()``.
    Injected clients are never closed by this class.

    Use as an async context manager to guarantee cleanup::

        async with GreenhouseSource(token) as src:
            async for posting in src.list_jobs(filters):
                ...
    """

    name: str

    def __init__(self, board_token: str, client: httpx.AsyncClient | None = None) -> None:
        self._board_token = board_token
        if client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
            )
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False
        self.name = f"greenhouse:{board_token}"

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
        url = f"{_BASE_URL}/{self._board_token}/jobs"
        params = {"content": "true"}
        try:
            resp = await _retry(self._client.get)(url, params=params)
            await asyncio.sleep(_RATE_LIMIT_SLEEP)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error(
                "Greenhouse list_jobs failed for board=%r: %s — "
                "check that the board token is a company identifier like 'anthropic', not a job title",
                self._board_token, exc,
            )
            return

        jobs = data.get("jobs", [])
        cutoff = _cutoff_dt(filters.posted_within_days, now=now)
        logger.info("Greenhouse board=%r: API returned %d jobs", self._board_token, len(jobs))

        yielded = 0
        filtered = 0
        for raw in jobs:
            try:
                posting = _parse_posting(raw, self._board_token)
            except Exception as exc:
                logger.warning("Greenhouse: failed to parse posting %s: %s", raw.get("id"), exc)
                continue

            if not _passes_filters(posting, filters, raw, cutoff):
                filtered += 1
                continue

            yielded += 1
            yield posting

        logger.info(
            "Greenhouse board=%r done: yielded=%d, filtered=%d",
            self._board_token, yielded, filtered,
        )

    async def fetch_job(self, source_id: str) -> RawJobPosting:
        url = f"{_BASE_URL}/{self._board_token}/jobs/{source_id}"
        resp = await _retry(self._client.get)(url)
        await asyncio.sleep(_RATE_LIMIT_SLEEP)
        resp.raise_for_status()
        raw = resp.json()
        return _parse_posting(raw, self._board_token)


def _cutoff_dt(days: int, *, now: datetime | None = None) -> datetime:
    reference = now if now is not None else datetime.now(tz=UTC)
    return reference - timedelta(days=days)


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
