from __future__ import annotations

import builtins
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.job_posting import JobPosting
from app.db.models.match import Match
from app.scrapers.types import RawJobPosting

logger = logging.getLogger(__name__)

_LIKE_ESCAPE = "\\"

# Source categories whose stored value is "<category>:<token>" (board-backed).
# linkedin/mycareersfuture store the category verbatim, so they fall through to ==.
_PREFIXED_CATEGORIES = frozenset({"greenhouse", "lever"})

_DEFAULT_PAGE_LIMIT = 50
_MIN_PAGE_LIMIT = 1
_MAX_PAGE_LIMIT = 200


def _escape_like(value: str) -> str:
    """Escape backslash, percent, and underscore for use in a LIKE pattern."""
    return (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
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

    async def list_with_matches(
        self,
        user_id: uuid.UUID,
        *,
        source: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> builtins.list[builtins.tuple[JobPosting, Match | None]]:
        """Return job postings paired with the latest Match for *user_id*.

        Two queries are issued (jobs, then their matches) and the results are
        stitched in Python to avoid N+1 queries.

        Args:
            user_id: The user whose matches are fetched.
            source:  Optional exact filter on JobPosting.source.
            query:   Optional case-insensitive substring on title OR company.
            limit:   Maximum number of job postings to return.

        Returns:
            A list of (JobPosting, Match | None) tuples ordered by scraped_at desc.
        """
        jobs = await self.list(source=source, query=query, limit=limit)
        if not jobs:
            return []

        job_ids = [j.id for j in jobs]

        # Fetch the most-recent Match per job for this user in one query.
        # We use a subquery-free approach: fetch all matches for these jobs
        # then keep the one with the latest computed_at per job_id in Python.
        match_result = await self._session.execute(
            select(Match)
            .where(
                Match.user_id == user_id,
                Match.job_id.in_(job_ids),
            )
            .order_by(Match.computed_at.desc().nulls_last())
        )
        all_matches = list(match_result.scalars().all())

        # Build a map: job_id -> latest Match (by computed_at DESC NULLS LAST).
        # Because rows are ordered latest-first, the first occurrence per job_id
        # is always the most-recent — no further timestamp comparison needed.
        latest_match: dict[uuid.UUID, Match] = {}
        for m in all_matches:
            if m.job_id not in latest_match:
                latest_match[m.job_id] = m

        return [(job, latest_match.get(job.id)) for job in jobs]

    def _source_clause(self, source: str) -> ColumnElement[bool]:
        """Return a WHERE clause matching *source* by category or exact value.

        Board-backed categories (greenhouse/lever) match ``source LIKE '<cat>:%'``;
        keyword-backed categories (linkedin/mycareersfuture) match exactly. Any
        other value is treated as a full exact source string.
        """
        if source in _PREFIXED_CATEGORIES:
            pattern = f"{_escape_like(source)}:%"
            return JobPosting.source.like(pattern, escape=_LIKE_ESCAPE)
        # Exact categories (linkedin/mycareersfuture) and any full source string.
        return JobPosting.source == source

    def _apply_filters(
        self,
        stmt: Select,
        match_col: type[Match],
        *,
        source: str | None,
        query: str | None,
        company: str | None,
        location: str | None,
        scored: bool | None,
        min_fit: float | None,
        max_fit: float | None,
        posted_within_days: int | None,
    ) -> Select:
        """Apply all list-page filters to *stmt*. ``match_col`` is the joined Match alias."""
        if source is not None:
            stmt = stmt.where(self._source_clause(source))
        if query is not None:
            pattern = f"%{_escape_like(query)}%"
            stmt = stmt.where(
                or_(
                    JobPosting.title.ilike(pattern, escape=_LIKE_ESCAPE),
                    JobPosting.company.ilike(pattern, escape=_LIKE_ESCAPE),
                )
            )
        if company is not None:
            pattern = f"%{_escape_like(company)}%"
            stmt = stmt.where(JobPosting.company.ilike(pattern, escape=_LIKE_ESCAPE))
        if location is not None:
            pattern = f"%{_escape_like(location)}%"
            stmt = stmt.where(JobPosting.location.ilike(pattern, escape=_LIKE_ESCAPE))
        if scored is True:
            stmt = stmt.where(match_col.id.isnot(None))
        elif scored is False:
            stmt = stmt.where(match_col.id.is_(None))
        if min_fit is not None:
            stmt = stmt.where(match_col.overall_score >= min_fit)
        if max_fit is not None:
            stmt = stmt.where(match_col.overall_score <= max_fit)
        if posted_within_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=posted_within_days)
            stmt = stmt.where(JobPosting.scraped_at >= cutoff)
        return stmt

    async def list_page(
        self,
        user_id: uuid.UUID,
        *,
        source: str | None = None,
        query: str | None = None,
        company: str | None = None,
        location: str | None = None,
        scored: bool | None = None,
        min_fit: float | None = None,
        max_fit: float | None = None,
        posted_within_days: int | None = None,
        sort: Literal["recent", "fit"] = "recent",
        limit: int = _DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> builtins.tuple[builtins.list[builtins.tuple[JobPosting, Match | None]], int]:
        """Return a filtered, sorted, paginated page of (JobPosting, latest Match).

        The latest Match per (user, job) is selected with a ``row_number()`` window
        function and LEFT-JOINed so the ``scored``/``min_fit``/``max_fit`` filters and
        the ``fit`` sort run in SQL. Works on both SQLite and Postgres.

        Returns ``(rows, total)`` where ``total`` ignores limit/offset.
        """
        limit = max(_MIN_PAGE_LIMIT, min(limit, _MAX_PAGE_LIMIT))
        offset = max(0, offset)

        # Latest match per job for this user via window function (rn == 1).
        rn = (
            func.row_number()
            .over(
                partition_by=Match.job_id,
                order_by=Match.computed_at.desc().nulls_last(),
            )
            .label("rn")
        )
        ranked = select(Match, rn).where(Match.user_id == user_id).subquery()
        # Only keep the latest match per job (rn == 1) before joining.
        latest_sq = select(ranked).where(ranked.c.rn == 1).subquery()
        latest = aliased(Match, latest_sq)

        # Reference the ALIASED entity's column (not the raw subquery .c column) so
        # the ON-clause is consistent with the filters/sort, which all use ``latest``.
        join_on = latest.job_id == JobPosting.id
        base = select(JobPosting, latest).outerjoin(latest, join_on)
        base = self._apply_filters(
            base,
            latest,
            source=source,
            query=query,
            company=company,
            location=location,
            scored=scored,
            min_fit=min_fit,
            max_fit=max_fit,
            posted_within_days=posted_within_days,
        )

        # total: count of matching jobs, ignoring limit/offset.
        count_stmt = select(func.count()).select_from(base.order_by(None).subquery())
        total = int((await self._session.execute(count_stmt)).scalar_one())

        if sort == "fit":
            base = base.order_by(
                latest.overall_score.desc().nulls_last(),
                JobPosting.scraped_at.desc(),
            )
        else:
            base = base.order_by(JobPosting.scraped_at.desc())

        base = base.limit(limit).offset(offset)
        result = await self._session.execute(base)
        rows = [(job, match) for job, match in result.all()]
        return rows, total

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
            company_logo_url=raw.logo_url,
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
