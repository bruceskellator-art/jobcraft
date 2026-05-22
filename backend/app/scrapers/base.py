from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.scrapers.types import JobFilters, RawJobPosting


class JobSource(Protocol):
    name: str

    async def list_jobs(self, filters: JobFilters) -> AsyncIterator[RawJobPosting]: ...

    async def fetch_job(self, source_id: str) -> RawJobPosting: ...
