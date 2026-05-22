from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.scrapers.lever import LeverSource
from app.scrapers.types import JobFilters

_FIXTURES = Path(__file__).parent / "fixtures"


def _make_transport(postings: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        parts = path.rstrip("/").split("/")
        # /v0/postings/{company}/{id} vs /v0/postings/{company}
        if len(parts) >= 5 and parts[4]:  # has a job id
            job_id = parts[4]
            for p in postings:
                if p["id"] == job_id:
                    return httpx.Response(200, json=p)
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json=postings)

    return httpx.MockTransport(handler)


@pytest.fixture()
def postings_data() -> list:
    return json.loads((_FIXTURES / "lever_jobs.json").read_text())


@pytest.fixture()
def source(postings_data: list) -> LeverSource:
    transport = _make_transport(postings_data)
    client = httpx.AsyncClient(transport=transport)
    return LeverSource(company="acme", client=client)


class TestLeverListJobs:
    async def test_parses_recent_postings(self, source: LeverSource) -> None:
        # Arrange
        filters = JobFilters(posted_within_days=365)

        # Act
        postings = [p async for p in source.list_jobs(filters)]

        # Assert — 2 recent, 1 old (Sept 2001)
        assert len(postings) == 2

    async def test_keyword_filter_narrows_results(self, source: LeverSource) -> None:
        # Arrange
        filters = JobFilters(keywords=["backend"], posted_within_days=365)

        # Act
        postings = [p async for p in source.list_jobs(filters)]

        # Assert
        assert len(postings) == 1
        assert postings[0].title == "Backend Engineer"

    async def test_malformed_posting_skipped_without_raising(self, postings_data: list) -> None:
        # Arrange — inject a malformed posting (missing id) into the data
        broken = [{"text": "No ID Job"}] + postings_data

        transport = _make_transport(broken)
        client = httpx.AsyncClient(transport=transport)
        source = LeverSource(company="acme", client=client)
        filters = JobFilters(posted_within_days=365)

        # Act — should not raise
        postings = [p async for p in source.list_jobs(filters)]

        # Assert — valid ones still returned
        assert len(postings) == 2
        titles = [p.title for p in postings]
        assert "Backend Engineer" in titles

    async def test_fetch_job_returns_single_posting(self, source: LeverSource) -> None:
        # Arrange / Act
        posting = await source.fetch_job("abc-123")

        # Assert
        assert posting.title == "Backend Engineer"
        assert posting.source_id == "abc-123"
        assert posting.source == "lever:acme"


class TestLeverFiltering:
    async def test_date_filter_excludes_old_jobs(self, source: LeverSource) -> None:
        # Arrange — tight 30-day window
        filters = JobFilters(posted_within_days=30)

        # Act
        postings = [p async for p in source.list_jobs(filters)]

        # Assert — old job (Sept 2001) excluded
        titles = [p.title for p in postings]
        assert "Sales Manager" not in titles
