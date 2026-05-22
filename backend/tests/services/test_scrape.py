from __future__ import annotations

import json
from collections.abc import AsyncIterator

from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.scrapers.types import JobFilters, RawJobPosting
from app.services.scrape import run_scrape

# ---------------------------------------------------------------------------
# Helpers / Fake sources
# ---------------------------------------------------------------------------

_FILTERS = JobFilters()

_RAW_A = RawJobPosting(
    source="fake:alpha",
    source_url="https://example.com/jobs/1",
    source_id="job-1",
    company="Alpha Corp",
    title="Software Engineer",
    location="Remote",
    remote_policy="remote",
    raw_content="We are hiring a software engineer.",
)

_RAW_B = RawJobPosting(
    source="fake:alpha",
    source_url="https://example.com/jobs/2",
    source_id="job-2",
    company="Alpha Corp",
    title="Product Manager",
    location="New York",
    remote_policy=None,
    raw_content="We are hiring a product manager.",
)

_VALID_EXTRACTED = {
    "company": "Alpha Corp",
    "title": "Software Engineer",
    "seniority": "mid",
    "location": "Remote",
    "remote_policy": "remote",
    "salary_min_usd": None,
    "salary_max_usd": None,
    "required_skills": ["Python"],
    "preferred_skills": [],
    "responsibilities": ["Write code"],
    "qualifications": ["3+ years"],
    "culture_signals": [],
    "summary": "A software engineering role at Alpha Corp.",
}


class FakeSource:
    """Yields a fixed list of RawJobPostings. No network calls."""

    def __init__(self, name: str, postings: list[RawJobPosting]) -> None:
        self.name = name
        self._postings = postings

    async def list_jobs(self, filters: JobFilters) -> AsyncIterator[RawJobPosting]:
        for posting in self._postings:
            yield posting

    async def fetch_job(self, source_id: str) -> RawJobPosting:
        raise NotImplementedError


class FakeSourceRaisesAfterFirst:
    """Yields one posting then raises mid-iteration to test error isolation."""

    def __init__(self, name: str, first_posting: RawJobPosting) -> None:
        self.name = name
        self._posting = first_posting

    async def list_jobs(self, filters: JobFilters) -> AsyncIterator[RawJobPosting]:
        yield self._posting
        raise RuntimeError("Simulated mid-iteration failure")

    async def fetch_job(self, source_id: str) -> RawJobPosting:
        raise NotImplementedError


class FakeSourceAlwaysRaises:
    """Raises immediately on list_jobs to test full-source failure."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def list_jobs(self, filters: JobFilters) -> AsyncIterator[RawJobPosting]:
        raise RuntimeError("Simulated source failure")
        # Make this an async generator
        yield  # type: ignore[misc]

    async def fetch_job(self, source_id: str) -> RawJobPosting:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunScrapeNewPostings:
    """New postings are persisted and returned."""

    async def test_new_postings_are_created(self, session) -> None:
        # Arrange
        source = FakeSource("fake:alpha", [_RAW_A, _RAW_B])

        # Act
        created, logs = await run_scrape(session, [source], _FILTERS)
        await session.commit()

        # Assert
        assert len(created) == 2
        assert len(logs) == 1
        log = logs[0]
        assert log.source == "fake:alpha"
        assert log.total_new == 2
        assert log.total_listed == 2
        assert log.total_failed == 0

    async def test_created_postings_have_correct_fields(self, session) -> None:
        # Arrange
        source = FakeSource("fake:alpha", [_RAW_A])

        # Act
        created, _ = await run_scrape(session, [source], _FILTERS)
        await session.commit()

        # Assert
        posting = created[0]
        assert posting.source == "fake:alpha"
        assert posting.source_id == "job-1"
        assert posting.title == "Software Engineer"
        assert posting.company == "Alpha Corp"


class TestRunScrapeDeduplication:
    """Postings whose (source, source_id) already exist in DB are skipped."""

    async def test_duplicate_posting_is_skipped(self, session) -> None:
        # Arrange — first scrape persists job-1
        source_first = FakeSource("fake:alpha", [_RAW_A])
        await run_scrape(session, [source_first], _FILTERS)
        await session.commit()

        # Act — second scrape tries to insert the same posting
        source_second = FakeSource("fake:alpha", [_RAW_A])
        created, logs = await run_scrape(session, [source_second], _FILTERS)
        await session.commit()

        # Assert — nothing new created
        assert len(created) == 0
        assert logs[0].total_new == 0

    async def test_new_posting_alongside_duplicate_is_created(self, session) -> None:
        # Arrange — seed job-1
        source_first = FakeSource("fake:alpha", [_RAW_A])
        await run_scrape(session, [source_first], _FILTERS)
        await session.commit()

        # Act — second scrape has both job-1 (dup) and job-2 (new)
        source_second = FakeSource("fake:alpha", [_RAW_A, _RAW_B])
        created, logs = await run_scrape(session, [source_second], _FILTERS)
        await session.commit()

        # Assert — only job-2 is new
        assert len(created) == 1
        assert created[0].source_id == "job-2"
        assert logs[0].total_new == 1


class TestRunScrapeErrorIsolation:
    """A failing source must not abort results from other sources."""

    async def test_raising_source_isolated_others_still_produce_results(
        self, session
    ) -> None:
        # Arrange — one healthy source, one that always raises
        good_source = FakeSource("fake:good", [_RAW_A])
        bad_source = FakeSourceAlwaysRaises("fake:bad")

        # Act
        created, logs = await run_scrape(session, [good_source, bad_source], _FILTERS)
        await session.commit()

        # Assert — good source's posting was saved
        assert len(created) == 1
        assert created[0].source_id == "job-1"

        # Two logs: one per source
        assert len(logs) == 2
        good_log = next(lg for lg in logs if lg.source == "fake:good")
        bad_log = next(lg for lg in logs if lg.source == "fake:bad")
        assert good_log.total_new == 1
        assert bad_log.total_failed >= 1

    async def test_mid_iteration_raise_counts_failed_but_keeps_prior_result(
        self, session
    ) -> None:
        # Arrange — source yields one posting then raises
        raw_first = RawJobPosting(
            source="fake:partial",
            source_url="https://example.com/jobs/10",
            source_id="job-10",
            company="Partial Co",
            title="Engineer",
            location=None,
            remote_policy=None,
            raw_content="Some content.",
        )
        source = FakeSourceRaisesAfterFirst("fake:partial", raw_first)

        # Act
        created, logs = await run_scrape(session, [source], _FILTERS)
        await session.commit()

        # Assert — the first posting was saved before the raise
        assert len(created) == 1
        assert created[0].source_id == "job-10"
        # The raise itself is counted in failed
        assert logs[0].total_failed >= 1


class TestRunScrapeExtraction:
    """extract=True with a working LLMClient stores extracted dict on posting."""

    async def test_extract_true_stores_extracted_dict(self, session) -> None:
        # Arrange
        adapter = MockAdapter(responses=[json.dumps(_VALID_EXTRACTED)])
        llm = LLMClient(session=session, adapter=adapter)
        source = FakeSource("fake:alpha", [_RAW_A])

        # Act
        created, _ = await run_scrape(
            session, [source], _FILTERS, llm=llm, extract=True
        )
        await session.commit()

        # Assert
        assert len(created) == 1
        posting = created[0]
        assert posting.extracted is not None
        assert posting.extracted["company"] == "Alpha Corp"
        assert posting.extracted["required_skills"] == ["Python"]

    async def test_extract_false_leaves_extracted_null(self, session) -> None:
        # Arrange
        source = FakeSource("fake:alpha", [_RAW_A])

        # Act
        created, _ = await run_scrape(session, [source], _FILTERS, extract=False)
        await session.commit()

        # Assert
        assert created[0].extracted is None

    async def test_extract_true_no_llm_leaves_extracted_null(self, session) -> None:
        # Arrange — extract=True but no llm provided
        source = FakeSource("fake:alpha", [_RAW_A])

        # Act
        created, _ = await run_scrape(
            session, [source], _FILTERS, llm=None, extract=True
        )
        await session.commit()

        # Assert — graceful: no extraction, no crash
        assert created[0].extracted is None
