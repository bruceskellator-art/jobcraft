from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.scrapers.greenhouse import GreenhouseSource
from app.scrapers.types import JobFilters

_FIXTURES = Path(__file__).parent / "fixtures"


def _make_transport(jobs_data: dict) -> httpx.MockTransport:
    """Return a MockTransport that serves board listing + per-job detail."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/jobs"):
            return httpx.Response(200, json=jobs_data)
        # per-job fetch — return the first job that matches the id in the path
        job_id = int(path.split("/")[-1])
        for job in jobs_data["jobs"]:
            if job["id"] == job_id:
                return httpx.Response(200, json=job)
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.fixture()
def jobs_data() -> dict:
    return json.loads((_FIXTURES / "greenhouse_jobs.json").read_text())


@pytest.fixture()
def source(jobs_data: dict) -> GreenhouseSource:
    transport = _make_transport(jobs_data)
    client = httpx.AsyncClient(transport=transport)
    return GreenhouseSource(board_token="acme", client=client)


class TestGreenhouseListJobs:
    async def test_parses_recent_postings(self, source: GreenhouseSource) -> None:
        # Arrange
        filters = JobFilters(posted_within_days=365)  # wide window to capture all fixtures

        # Act
        postings = [p async for p in source.list_jobs(filters)]

        # Assert — 2 recent jobs pass; 2025-01-01 is ~540 days ago, outside 365d window
        assert len(postings) == 2

    async def test_keyword_filter_narrows_results(self, source: GreenhouseSource) -> None:
        # Arrange
        filters = JobFilters(keywords=["software engineer"], posted_within_days=365)

        # Act
        postings = [p async for p in source.list_jobs(filters)]

        # Assert — only "Software Engineer" matches
        assert len(postings) == 1
        assert postings[0].title == "Software Engineer"

    async def test_malformed_posting_skipped_without_raising(self, jobs_data: dict) -> None:
        # Arrange — inject a malformed job (missing title) into the data
        broken = jobs_data.copy()
        broken["jobs"] = [{"id": 9999}] + broken["jobs"]  # missing title -> parse fails

        transport = _make_transport(broken)
        client = httpx.AsyncClient(transport=transport)
        source = GreenhouseSource(board_token="acme", client=client)
        filters = JobFilters(posted_within_days=365)

        # Act — should not raise
        postings = [p async for p in source.list_jobs(filters)]

        # Assert — malformed posting is skipped; valid ones still returned
        assert len(postings) >= 2
        titles = [p.title for p in postings]
        assert "Software Engineer" in titles

    async def test_fetch_job_returns_single_posting(self, source: GreenhouseSource) -> None:
        # Arrange / Act
        posting = await source.fetch_job("1001")

        # Assert
        assert posting.title == "Software Engineer"
        assert posting.source_id == "1001"
        assert posting.source == "greenhouse:acme"


class TestGreenhouseFiltering:
    async def test_date_filter_excludes_old_jobs(self, source: GreenhouseSource) -> None:
        # Arrange — 30-day window; the 2025-01-01 job should be excluded
        filters = JobFilters(posted_within_days=30)

        # Act
        postings = [p async for p in source.list_jobs(filters)]

        # Assert — old job (2025-01-01) is excluded
        titles = [p.title for p in postings]
        assert "Product Manager" not in titles
