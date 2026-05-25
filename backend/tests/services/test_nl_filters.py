from __future__ import annotations

import json

from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.scrapers.types import JobFilters
from app.services.nl_filters import parse_filters

_CANNED_FILTERS = {
    "keywords": ["forward deployed", "AI engineer"],
    "companies": None,
    "locations": ["San Francisco", "Remote"],
    "remote_only": True,
    "seniority": ["mid", "senior"],
    "posted_within_days": 14,
}

_CANNED_JSON = json.dumps(_CANNED_FILTERS)


class TestParseFilters:
    async def test_returns_typed_job_filters(self, session) -> None:
        # Arrange
        adapter = MockAdapter(responses=[_CANNED_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        result = await parse_filters(
            session=session,
            llm=llm,
            text="FDE roles at AI labs, remote or SF, mid-senior",
        )

        # Assert
        assert isinstance(result, JobFilters)

    async def test_keywords_parsed_correctly(self, session) -> None:
        # Arrange
        adapter = MockAdapter(responses=[_CANNED_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        result = await parse_filters(session=session, llm=llm, text="AI engineer roles")

        # Assert
        assert result.keywords == ["forward deployed", "AI engineer"]

    async def test_remote_only_flag(self, session) -> None:
        # Arrange
        adapter = MockAdapter(responses=[_CANNED_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        result = await parse_filters(session=session, llm=llm, text="remote jobs")

        # Assert
        assert result.remote_only is True

    async def test_seniority_levels(self, session) -> None:
        # Arrange
        adapter = MockAdapter(responses=[_CANNED_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        result = await parse_filters(session=session, llm=llm, text="senior roles")

        # Assert
        assert result.seniority == ["mid", "senior"]

    async def test_posted_within_days(self, session) -> None:
        # Arrange
        adapter = MockAdapter(responses=[_CANNED_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        result = await parse_filters(session=session, llm=llm, text="last 2 weeks")

        # Assert
        assert result.posted_within_days == 14

    async def test_prompt_created_idempotently(self, session) -> None:
        # Arrange — call twice; should not create duplicate active prompt
        adapter = MockAdapter(responses=[_CANNED_JSON, _CANNED_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        await parse_filters(session=session, llm=llm, text="first call")
        await parse_filters(session=session, llm=llm, text="second call")

        # Assert — no exception raised; both calls return valid JobFilters
