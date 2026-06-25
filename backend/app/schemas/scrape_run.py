from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.job import ScrapeRunLogView


class ScrapeRunView(BaseModel):
    """Response schema for a background scrape run."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    status: str
    request: dict | None = None
    total_created: int
    runs: list[ScrapeRunLogView] | None = None
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
