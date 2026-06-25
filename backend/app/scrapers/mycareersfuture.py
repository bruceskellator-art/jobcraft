"""MyCareersFuture (MCF) job board adapter.

Uses the public MCF API v2 at https://api.mycareersfuture.gov.sg/v2/jobs.
Paginates up to ``max_pages`` pages of 100 results each, filters by date and
keywords, then yields ``RawJobPosting`` instances.

MCF is Singapore's national jobs portal and is the primary source for
Singapore-based listings.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
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

_API_BASE = "https://api.mycareersfuture.gov.sg/v2/jobs"
_JOB_URL_BASE = "https://www.mycareersfuture.gov.sg/job"
_PAGE_SIZE = 100
_MAX_PAGES = 10
_RATE_LIMIT_SLEEP = 0.3  # seconds between requests — be polite to the gov API


def _is_retryable(exc: BaseException) -> bool:
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
    wait=wait_exponential_jitter(initial=1, max=15),
    reraise=True,
)


class _HTMLStripper(HTMLParser):
    """Minimal HTML → plain text stripper for MCF description fields."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def get_text(self) -> str:
        return " ".join(chunk.strip() for chunk in self._chunks if chunk.strip())


def _strip_html(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


class MyCareersFutureSource:
    """Adapter for the MyCareersFuture public jobs API.

    Usage::

        async with MyCareersFutureSource(keywords=["data engineer"]) as src:
            async for posting in src.list_jobs(filters):
                ...

    The *keywords* list is joined into the API ``search`` parameter.
    When *keywords* is empty, the scraper issues a broad search with no
    keyword constraint and relies on ``filters.keywords`` for post-filtering.
    """

    name: str = "mycareersfuture"

    def __init__(
        self,
        keywords: list[str] | None = None,
        client: httpx.AsyncClient | None = None,
        max_pages: int = _MAX_PAGES,
    ) -> None:
        self._keywords = keywords or []
        self._max_pages = max_pages
        if client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
                headers={
                    "User-Agent": "JobCraft/1.0 (job search assistant; +https://github.com/jobcraft)",
                    "Accept": "application/json",
                },
            )
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False

    async def aclose(self) -> None:
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
        cutoff = _cutoff_dt(filters.posted_within_days, now=now)
        search_term = " ".join(self._keywords) if self._keywords else ""

        for page in range(self._max_pages):
            params: dict[str, str | int] = {
                "limit": _PAGE_SIZE,
                "page": page,
                "sortBy": "new_posting_date",
            }
            if search_term:
                params["search"] = search_term

            try:
                resp = await _retry(self._client.get)(_API_BASE, params=params)
                await asyncio.sleep(_RATE_LIMIT_SLEEP)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.error("MCF list_jobs failed on page %d: %s", page, exc)
                return

            results = data.get("results") or []
            total_from_api = data.get("total", 0)
            logger.info(
                "MCF page %d: API returned %d items (grand total=%d, search=%r)",
                page, len(results), total_from_api, search_term or "<none>",
            )
            if not results:
                break  # no more pages

            page_yielded = 0
            page_date_filtered = 0
            page_kw_filtered = 0
            for raw in results:
                try:
                    posting = _parse_posting(raw)
                except Exception as exc:
                    logger.warning("MCF: failed to parse posting %s: %s", raw.get("uuid"), exc)
                    continue

                try:
                    meta = raw.get("metadata")
                    posted_dt = _parse_dt((meta or {}).get("newPostingDate"))
                except Exception:
                    posted_dt = None

                if posted_dt is not None and posted_dt < cutoff:
                    page_date_filtered += 1
                    # Results are sorted newest-first; once we're past the cutoff,
                    # all remaining items on this and later pages will also be stale.
                    logger.info(
                        "MCF page %d: reached date cutoff after %d items (%d passed, %d kw-filtered)",
                        page, page_yielded + page_date_filtered + page_kw_filtered,
                        page_yielded, page_kw_filtered,
                    )
                    return

                if not _passes_filters(posting, filters):
                    page_kw_filtered += 1
                    continue

                page_yielded += 1
                yield posting

            logger.info(
                "MCF page %d done: yielded=%d, date-filtered=%d, kw-filtered=%d",
                page, page_yielded, page_date_filtered, page_kw_filtered,
            )
            fetched_so_far = (page + 1) * _PAGE_SIZE
            if fetched_so_far >= total_from_api:
                break  # exhausted all results

        # Unreachable except through return/break above, but satisfies AsyncIterator
        return

    async def fetch_job(self, source_id: str) -> RawJobPosting:
        """Fetch a single posting by MCF UUID."""
        url = f"{_API_BASE}/{source_id}"
        resp = await _retry(self._client.get)(url)
        await asyncio.sleep(_RATE_LIMIT_SLEEP)
        resp.raise_for_status()
        raw = resp.json()
        return _parse_posting(raw)


def _cutoff_dt(days: int, *, now: datetime | None = None) -> datetime:
    reference = now if now is not None else datetime.now(tz=UTC)
    return reference - timedelta(days=days)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # MCF returns date-only strings like '2026-06-25' — treat as UTC midnight
        # to avoid TypeError when comparing against the UTC-aware cutoff.
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def _parse_posting(raw: dict) -> RawJobPosting:
    """Parse an MCF API job dict into RawJobPosting. Raises on missing required fields."""
    job_uuid: str = raw["uuid"]
    title: str = raw["title"]
    company: str = (raw.get("company") or {}).get("name") or "Unknown"
    source_url = f"{_JOB_URL_BASE}/{job_uuid}"

    # Location: MCF uses region/district, not a single string
    address = raw.get("address") or {}
    region = address.get("region") or ""
    location_parts = [p for p in [region, "Singapore"] if p]
    location = ", ".join(location_parts) if location_parts else "Singapore"

    # Remote policy
    is_remote = raw.get("isRemote", False)
    remote_policy = "remote" if is_remote else None

    # Build a readable content block for the LLM extractor
    description_html = raw.get("description") or ""
    description_text = _strip_html(description_html)

    skills: list[str] = [
        s.get("skill", "") for s in (raw.get("skills") or []) if s.get("skill")
    ]
    position_levels: list[str] = [
        pl.get("position", "") for pl in (raw.get("positionLevels") or []) if pl.get("position")
    ]
    employment_types: list[str] = [
        et.get("employmentType", "") for et in (raw.get("employmentTypes") or []) if et.get("employmentType")
    ]
    salary = raw.get("salary") or {}
    salary_min = salary.get("minimum")
    salary_max = salary.get("maximum")
    salary_type = salary.get("type", "Monthly")

    raw_parts: list[str] = [f"Title: {title}", f"Company: {company}", f"Location: {location}"]
    if position_levels:
        raw_parts.append(f"Level: {', '.join(position_levels)}")
    if employment_types:
        raw_parts.append(f"Employment type: {', '.join(employment_types)}")
    if salary_min and salary_max:
        raw_parts.append(f"Salary: SGD {salary_min:,}–{salary_max:,} {salary_type}")
    elif salary_min:
        raw_parts.append(f"Salary: from SGD {salary_min:,} {salary_type}")
    if skills:
        raw_parts.append(f"Skills: {', '.join(skills)}")
    if description_text:
        raw_parts.append(description_text)

    return RawJobPosting(
        source="mycareersfuture",
        source_url=source_url,
        source_id=job_uuid,
        company=company,
        title=title,
        location=location,
        remote_policy=remote_policy,
        raw_content="\n\n".join(raw_parts),
    )


def _passes_filters(posting: RawJobPosting, filters: JobFilters) -> bool:
    if filters.keywords:
        haystack = f"{posting.title} {posting.raw_content}".lower()
        if not any(kw.lower() in haystack for kw in filters.keywords):
            return False

    if filters.companies:
        if not any(c.lower() in posting.company.lower() for c in filters.companies):
            return False

    if filters.remote_only:
        if posting.remote_policy != "remote":
            content_lower = posting.raw_content.lower()
            if "remote" not in content_lower and "remote" not in posting.title.lower():
                return False

    return True
