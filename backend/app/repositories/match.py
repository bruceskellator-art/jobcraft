from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.match import Match


class MatchRepository:
    """Data-access layer for Match records.

    Mutating methods flush within the session transaction but do NOT commit.
    The caller is responsible for committing or rolling back, keeping the
    transaction boundary at the service/HTTP-request level.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        user_id: uuid.UUID,
        job_id: uuid.UUID,
        prompt_version_id: uuid.UUID,
    ) -> Match | None:
        """Return a Match by its composite natural key, or None if absent."""
        result = await self._session.execute(
            select(Match).where(
                Match.user_id == user_id,
                Match.job_id == job_id,
                Match.prompt_version_id == prompt_version_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: uuid.UUID,
        job_id: uuid.UUID,
        prompt_version_id: uuid.UUID,
        overall_score: float,
        dimension_scores: dict,
        gaps: list,
        rationale: str,
    ) -> Match:
        """Insert a new Match or update the existing one for the composite key.

        Flushes to the session; caller must commit.
        """
        existing = await self.get(user_id, job_id, prompt_version_id)
        if existing is not None:
            await self._session.execute(
                update(Match)
                .where(Match.id == existing.id)
                .values(
                    overall_score=overall_score,
                    dimension_scores=dimension_scores,
                    gaps=gaps,
                    rationale=rationale,
                )
            )
            await self._session.flush()
            await self._session.refresh(existing)
            return existing

        match = Match(
            id=uuid.uuid4(),
            user_id=user_id,
            job_id=job_id,
            prompt_version_id=prompt_version_id,
            overall_score=overall_score,
            dimension_scores=dimension_scores,
            gaps=gaps,
            rationale=rationale,
        )
        self._session.add(match)
        await self._session.flush()
        await self._session.refresh(match)
        return match
