"""ApplyStrategy protocol and concrete implementations.

Each strategy pairs a FormSource (how to render/submit the form) with the
map_fields agent (how to fill it).  select_strategy picks the first strategy
whose can_handle returns True; GenericFormStrategy is always appended last as
a catch-all fallback.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.apply.browser import FormSource
from app.apply.field_mapper import map_fields
from app.apply.types import ApplyOutcome, FieldMap
from app.embeddings.base import EmbeddingClient
from app.vectorstore.base import VectorStore

if TYPE_CHECKING:
    from app.db.models.application import Application
    from app.db.models.job_posting import JobPosting
    from app.llm.client import LLMClient

logger = logging.getLogger(__name__)

_GREENHOUSE_SOURCE = "greenhouse"


class ApplyStrategy(Protocol):
    """Protocol that every apply strategy must satisfy."""

    name: str

    def can_handle(self, job: JobPosting) -> bool: ...

    async def fill(
        self,
        app: Application,
        job: JobPosting,
        session: AsyncSession,
        llm: LLMClient | None,
        embed: EmbeddingClient,
        store: VectorStore,
        user_id: uuid.UUID,
        *,
        cover_letter: str | None = None,
    ) -> FieldMap: ...

    async def submit(
        self,
        job: JobPosting,
        field_map: FieldMap,
    ) -> ApplyOutcome: ...


class GenericFormStrategy:
    """Fallback strategy for arbitrary career-page forms."""

    name: str = "generic"

    def __init__(self, form_source: FormSource) -> None:
        self._form_source = form_source

    def can_handle(self, job: JobPosting) -> bool:
        return True  # always handles as a fallback

    async def fill(
        self,
        app: Application,
        job: JobPosting,
        session: AsyncSession,
        llm: LLMClient | None,
        embed: EmbeddingClient,
        store: VectorStore,
        user_id: uuid.UUID,
        *,
        cover_letter: str | None = None,
    ) -> FieldMap:
        fields = await self._form_source.render_form(job, app)
        return await map_fields(
            session,
            llm,
            embed,
            store,
            user_id,
            job,
            fields,
            cover_letter=cover_letter,
        )

    async def submit(
        self,
        job: JobPosting,
        field_map: FieldMap,
    ) -> ApplyOutcome:
        return await self._form_source.submit_form(job, field_map)


class GreenhouseFormStrategy:
    """Strategy for Greenhouse-hosted application forms."""

    name: str = "greenhouse"

    def __init__(self, form_source: FormSource) -> None:
        self._form_source = form_source

    def can_handle(self, job: JobPosting) -> bool:
        return job.source == _GREENHOUSE_SOURCE

    async def fill(
        self,
        app: Application,
        job: JobPosting,
        session: AsyncSession,
        llm: LLMClient | None,
        embed: EmbeddingClient,
        store: VectorStore,
        user_id: uuid.UUID,
        *,
        cover_letter: str | None = None,
    ) -> FieldMap:
        fields = await self._form_source.render_form(job, app)
        return await map_fields(
            session,
            llm,
            embed,
            store,
            user_id,
            job,
            fields,
            cover_letter=cover_letter,
        )

    async def submit(
        self,
        job: JobPosting,
        field_map: FieldMap,
    ) -> ApplyOutcome:
        return await self._form_source.submit_form(job, field_map)


def select_strategy(
    job: JobPosting,
    strategies: list[ApplyStrategy],
) -> ApplyStrategy:
    """Return the first strategy that can handle job.

    The caller is responsible for ordering strategies with the most specific
    first and GenericFormStrategy last as a fallback.
    """
    for strategy in strategies:
        if strategy.can_handle(job):
            return strategy
    raise ValueError(
        f"No strategy can handle job source '{job.source}'. "
        "Ensure GenericFormStrategy is included as a fallback."
    )
