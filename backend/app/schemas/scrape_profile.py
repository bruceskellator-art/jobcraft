from __future__ import annotations

from pydantic import BaseModel


class ScrapeProfileConfig(BaseModel):
    linkedin_keywords: list[str] = []
    mcf_keywords: list[str] = []
    greenhouse_boards: list[str] = []
    lever_companies: list[str] = []
    posted_within_days: int = 30
    extract: bool = False
