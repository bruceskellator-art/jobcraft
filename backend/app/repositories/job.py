from __future__ import annotations

import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.job_posting import JobPosting
from app.scrapers.types import RawJobPosting

logger = logging.getLogger(__name__)

_LIKE_ESCAPE = "\\"


def _escape_like(value: str) -> str:
    """Escape backslash, percent, and underscore for use in a LIKE pattern."""
    return (
        value
        .replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )


class JobRepository:
    """Data-access layer for JobPosting records.

    Each mutating method flushes changes to the database within the
    session transaction but does NOT commit. The caller (router) is
    responsible for committing or rolling back.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        source: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> list[JobPosting]:
        """Return job postings with optional source and title/company filters.

        Args:
            source: Exact match on the source field (e.g. "greenhouse:acme").
            query: Case-insensitive substring match against title OR company.
                   Wildcards (%, _) in the query are treated as literals.
            limit: Maximum number of results to return.
        """
        stmt = select(JobPosting)
        if source is not None:
            stmt = stmt.where(JobPosting.source == source)
        if query is not None:
            pattern = f"%{_escape_like(query)}%"
            stmt = stmt.where(
                or_(
                    JobPosting.title.ilike(pattern, escape=_LIKE_ESCAPE),
                    JobPosting.company.ilike(pattern, escape=_LIKE_ESCAPE),
                )
            )
        stmt = stmt.order_by(JobPosting.scraped_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, job_id: object) -> JobPosting | None:
        """Return a single posting by primary key, or None if not found."""
        return await self._session.get(JobPosting, job_id)

    async def get_by_source(self, source: str, source_id: str) -> JobPosting | None:
        """Return a posting matching (source, source_id), or None."""
        result = await self._session.execute(
            select(JobPosting).where(
                JobPosting.source == source,
                JobPosting.source_id == source_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_from_raw(
        self,
        raw: RawJobPosting,
        extracted: dict | None,
    ) -> JobPosting:
        """Persist a new JobPosting from a RawJobPosting and optional extracted data.

        Flushes to the session so the returned object has server-generated
        defaults (id, scraped_at) populated. The caller must commit.
        """
        posting = JobPosting(
            source=raw.source,
            source_url=raw.source_url,
            source_id=raw.source_id,
            company=raw.company,
            title=raw.title,
            location=raw.location,
            remote_policy=raw.remote_policy,
            raw_content=raw.raw_content,
            extracted=extracted,
        )
        self._session.add(posting)
        await self._session.flush()
        await self._session.refresh(posting)
        return posting
