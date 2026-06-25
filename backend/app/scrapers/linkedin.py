"""LinkedIn public guest job board adapter.

Uses LinkedIn's unauthenticated guest endpoints — no credentials required.
Paginates up to ``_MAX_PAGES`` pages of 25 results each, sorted newest-first,
and short-circuits when postings fall outside the date cutoff.
"""

from __future__ import annotations

import asyncio
import logging
import re
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

_LIST_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
_PAGE_SIZE = 25
_MAX_PAGES = 4
_RATE_LIMIT_SLEEP = 1.0
_DETAIL_SLEEP = 0.5

_LI_RE = re.compile(r"<li>(.*?)</li>", re.DOTALL)
_URN_RE = re.compile(r'data-entity-urn="urn:li:jobPosting:(\d+)"')
_HREF_RE = re.compile(r'href="(https://www\.linkedin\.com/jobs/view/[^"?]+)')
_TITLE_RE = re.compile(r'class="base-search-card__title"[^>]*>\s*(.*?)\s*</', re.DOTALL)
_COMPANY_RE = re.compile(r'class="[^"]*hidden-nested-link[^"]*"[^>]*>\s*(.*?)\s*</a>', re.DOTALL)
_LOCATION_RE = re.compile(r'class="job-search-card__location"[^>]*>\s*(.*?)\s*</span>', re.DOTALL)
_DATE_RE = re.compile(r'datetime="(\d{4}-\d{2}-\d{2})"')
_DESC_RE = re.compile(r'<div class="show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', re.DOTALL)


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


class LinkedInSource:
    """Adapter for LinkedIn's public guest job search endpoints.

    Usage::

        async with LinkedInSource(keywords=["software engineer"]) as src:
            async for posting in src.list_jobs(filters):
                ...
    """

    name: str = "linkedin"

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
                    "User-Agent": "JobCraft/1.0 (job search assistant)",
                    "Accept": "text/html",
                },
                follow_redirects=True,
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
                "location": "Singapore",
                "start": page * _PAGE_SIZE,
            }
            if search_term:
                params["keywords"] = search_term

            try:
                resp = await _retry(self._client.get)(_LIST_URL, params=params)
                await asyncio.sleep(_RATE_LIMIT_SLEEP)
                resp.raise_for_status()
                html = resp.text
            except Exception as exc:
                logger.error("LinkedIn list_jobs failed on page %d: %s", page, exc)
                return

            items = _LI_RE.findall(html)
            logger.info(
                "LinkedIn page %d: found %d listings in HTML (keywords=%r)",
                page, len(items), search_term or "<none>",
            )
            if not items:
                break

            page_yielded = 0
            page_cutoff = False
            for item_html in items:
                try:
                    posting, posted_at = await self._parse_listing(item_html, filters)
                except Exception as exc:
                    logger.warning("LinkedIn: failed to parse listing: %s", exc)
                    continue

                if posted_at is not None and posted_at < cutoff:
                    logger.info(
                        "LinkedIn page %d: reached date cutoff after %d items yielded",
                        page, page_yielded,
                    )
                    return

                if posting is not None:
                    page_yielded += 1
                    yield posting

            logger.info("LinkedIn page %d done: yielded=%d of %d", page, page_yielded, len(items))

        return

    async def _parse_listing(
        self,
        item_html: str,
        filters: JobFilters,
    ) -> tuple[RawJobPosting | None, datetime | None]:
        urn_m = _URN_RE.search(item_html)
        job_id = urn_m.group(1) if urn_m else None

        href_m = _HREF_RE.search(item_html)
        source_url = href_m.group(1) if href_m else (
            f"https://www.linkedin.com/jobs/view/{job_id}" if job_id else ""
        )

        title_m = _TITLE_RE.search(item_html)
        title = _strip_html(title_m.group(1)) if title_m else "Unknown"

        company_m = _COMPANY_RE.search(item_html)
        company = _strip_html(company_m.group(1)) if company_m else "Unknown"

        location_m = _LOCATION_RE.search(item_html)
        location = _strip_html(location_m.group(1)) if location_m else "Singapore"

        date_m = _DATE_RE.search(item_html)
        posted_at: datetime | None = None
        if date_m:
            try:
                posted_at = datetime.fromisoformat(date_m.group(1)).replace(tzinfo=UTC)
            except ValueError:
                pass

        description = ""
        if job_id:
            description = await self._fetch_description(job_id)

        raw_parts = [f"Title: {title}", f"Company: {company}", f"Location: {location}"]
        if description:
            raw_parts.append(description)

        posting = RawJobPosting(
            source="linkedin",
            source_url=source_url,
            source_id=job_id,
            company=company,
            title=title,
            location=location,
            remote_policy=None,
            raw_content="\n\n".join(raw_parts),
        )

        if not _passes_filters(posting, filters):
            return None, posted_at

        return posting, posted_at

    async def _fetch_description(self, job_id: str) -> str:
        url = _DETAIL_URL.format(job_id=job_id)
        try:
            resp = await _retry(self._client.get)(url)
            await asyncio.sleep(_DETAIL_SLEEP)
            resp.raise_for_status()
            desc_m = _DESC_RE.search(resp.text)
            if desc_m:
                return _strip_html(desc_m.group(1))
        except Exception as exc:
            logger.warning("LinkedIn: description fetch failed for %s: %s", job_id, exc)
        return ""


def _cutoff_dt(days: int, *, now: datetime | None = None) -> datetime:
    reference = now if now is not None else datetime.now(tz=UTC)
    return reference - timedelta(days=days)


def _passes_filters(posting: RawJobPosting, filters: JobFilters) -> bool:
    if filters.keywords:
        haystack = f"{posting.title} {posting.raw_content}".lower()
        if not any(kw.lower() in haystack for kw in filters.keywords):
            return False

    if filters.companies:
        if not any(c.lower() in posting.company.lower() for c in filters.companies):
            return False

    if filters.remote_only:
        content_lower = posting.raw_content.lower()
        if "remote" not in content_lower and "remote" not in posting.title.lower():
            return False

    return True
