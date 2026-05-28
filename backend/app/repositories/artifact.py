"""Data-access layer for Artifact records.

Mutating methods flush within the session transaction but do NOT commit.
The caller (service/router) is responsible for committing or rolling back.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.artifact import Artifact


class ArtifactRepository:
    """Repository for Artifact persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: uuid.UUID,
        kind: str,
        format: str,
        content: str,
        *,
        job_id: uuid.UUID | None = None,
        is_baseline: bool = False,
        scores: dict | None = None,
        prompt_version_id: uuid.UUID | None = None,
        generation_run_id: uuid.UUID | None = None,
    ) -> Artifact:
        """Persist a new Artifact and flush to the session.

        Returns the new artifact with server-generated defaults (id, created_at)
        populated after the flush.
        """
        artifact = Artifact(
            id=uuid.uuid4(),
            user_id=user_id,
            job_id=job_id,
            kind=kind,
            format=format,
            content=content,
            is_baseline=is_baseline,
            scores=scores,
            prompt_version_id=prompt_version_id,
            generation_run_id=generation_run_id,
        )
        self._session.add(artifact)
        await self._session.flush()
        await self._session.refresh(artifact)
        return artifact

    async def get(self, artifact_id: uuid.UUID) -> Artifact | None:
        """Return a single artifact by primary key, or None if not found."""
        return await self._session.get(Artifact, artifact_id)

    async def list_by_user(self, user_id: uuid.UUID) -> list[Artifact]:
        """Return all artifacts belonging to user_id, newest first."""
        result = await self._session.execute(
            select(Artifact)
            .where(Artifact.user_id == user_id)
            .order_by(Artifact.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_for_job(
        self, user_id: uuid.UUID, job_id: uuid.UUID
    ) -> list[Artifact]:
        """Return all artifacts for a specific user+job pair, newest first."""
        result = await self._session.execute(
            select(Artifact)
            .where(Artifact.user_id == user_id, Artifact.job_id == job_id)
            .order_by(Artifact.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_baseline(self, user_id: uuid.UUID) -> Artifact | None:
        """Return the baseline artifact (uploaded résumé) for a user, or None."""
        result = await self._session.execute(
            select(Artifact).where(
                Artifact.user_id == user_id,
                Artifact.is_baseline == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()
