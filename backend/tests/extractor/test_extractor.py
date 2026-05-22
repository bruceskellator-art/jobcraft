from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.db.models.prompt_version import PromptVersion
from app.extractor.service import ensure_extract_prompt, extract_job
from app.extractor.types import ExtractedJob
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_JOB: dict = {
    "company": "Acme AI",
    "title": "Senior Software Engineer",
    "seniority": "senior",
    "location": "San Francisco, CA",
    "remote_policy": "hybrid",
    "salary_min_usd": 180000,
    "salary_max_usd": 240000,
    "required_skills": ["Python", "distributed systems"],
    "preferred_skills": ["Rust", "Kubernetes"],
    "responsibilities": ["Design scalable services", "Mentor junior engineers"],
    "qualifications": ["5+ years of backend experience"],
    "culture_signals": ["values move-fast", "research-oriented"],
    "summary": "Acme AI is hiring a senior engineer to lead backend infrastructure. "
    "You will design distributed systems at scale. Strong Python skills required.",
}

_VALID_RESPONSE = json.dumps(_VALID_JOB)
_INVALID_RESPONSE = "this is not valid json {"


def _make_llm(session, responses: list[str]) -> tuple[LLMClient, MockAdapter]:
    adapter = MockAdapter(responses=responses)
    client = LLMClient(session=session, adapter=adapter)
    return client, adapter


# ---------------------------------------------------------------------------
# Tests: ensure_extract_prompt
# ---------------------------------------------------------------------------


class TestEnsureExtractPrompt:
    async def test_creates_prompt_on_first_call(self, session) -> None:
        # Arrange — empty DB

        # Act
        prompt = await ensure_extract_prompt(session)

        # Assert
        assert prompt.name == "extract_job"
        assert prompt.version == 1
        assert prompt.is_active is True
        assert "{{ raw_content }}" in prompt.template
        assert "<job_posting>" in prompt.template

    async def test_idempotent_returns_same_row(self, session) -> None:
        # Arrange — seed once
        first = await ensure_extract_prompt(session)

        # Act — call again
        second = await ensure_extract_prompt(session)

        # Assert — same DB row, no duplicate
        assert first.id == second.id

    async def test_does_not_insert_duplicate_active_row(self, session) -> None:
        # Arrange
        await ensure_extract_prompt(session)
        await ensure_extract_prompt(session)

        # Assert — only one active row for this name
        result = await session.execute(
            select(PromptVersion).where(
                PromptVersion.name == "extract_job",
                PromptVersion.is_active == True,  # noqa: E712
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Tests: extract_job
# ---------------------------------------------------------------------------


class TestExtractJob:
    async def test_valid_response_returns_populated_extracted_job(
        self, session
    ) -> None:
        # Arrange
        llm, _ = _make_llm(session, [_VALID_RESPONSE])

        # Act
        result = await extract_job(session, llm, "We are hiring a senior engineer...")

        # Assert
        assert isinstance(result, ExtractedJob)
        assert result.company == "Acme AI"
        assert result.title == "Senior Software Engineer"
        assert result.seniority == "senior"
        assert result.location == "San Francisco, CA"
        assert result.remote_policy == "hybrid"
        assert result.salary_min_usd == 180000
        assert result.salary_max_usd == 240000
        assert result.required_skills == ["Python", "distributed systems"]
        assert result.preferred_skills == ["Rust", "Kubernetes"]
        assert len(result.responsibilities) == 2
        assert len(result.qualifications) == 1
        assert "values move-fast" in result.culture_signals
        assert len(result.summary) > 0

    async def test_first_invalid_second_valid_retries_and_returns_result(
        self, session
    ) -> None:
        # Arrange — first response is bad JSON, second is valid
        llm, adapter = _make_llm(session, [_INVALID_RESPONSE, _VALID_RESPONSE])

        # Act
        result = await extract_job(session, llm, "Some job posting text.")

        # Assert — parsed result returned after one retry
        assert isinstance(result, ExtractedJob)
        assert result.company == "Acme AI"
        # MockAdapter was called exactly twice
        assert len(adapter.calls) == 2

    async def test_both_responses_invalid_returns_none(self, session) -> None:
        # Arrange — both responses are bad JSON
        llm, adapter = _make_llm(
            session, [_INVALID_RESPONSE, _INVALID_RESPONSE]
        )

        # Act
        result = await extract_job(session, llm, "Some job posting text.")

        # Assert
        assert result is None
        assert len(adapter.calls) == 2

    async def test_empty_raw_content_raises_value_error(self, session) -> None:
        # Arrange
        llm, _ = _make_llm(session, [_VALID_RESPONSE])

        # Act / Assert
        with pytest.raises(ValueError, match="empty"):
            await extract_job(session, llm, "")

    async def test_whitespace_only_raw_content_raises_value_error(
        self, session
    ) -> None:
        # Arrange
        llm, _ = _make_llm(session, [_VALID_RESPONSE])

        # Act / Assert
        with pytest.raises(ValueError, match="empty"):
            await extract_job(session, llm, "   \n\t  ")
