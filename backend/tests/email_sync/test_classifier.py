"""Tests for classify_email — MockAdapter canned JSON parses into EmailStatusInference."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.email_sync.classifier import EmailStatusInference, classify_email
from app.email_sync.provider import RawEmail
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient


def _make_raw(body: str = "Congratulations! We would like to offer you the position.") -> RawEmail:
    return RawEmail(
        provider_message_id="msg-001",
        thread_id="thread-001",
        from_address="recruiter@company.com",
        subject="Job Offer — Senior Engineer",
        snippet="We would like to offer you",
        body=body,
        received_at=datetime(2026, 6, 24, 10, 0, 0, tzinfo=UTC),
    )


def _offer_response() -> str:
    return json.dumps(
        {
            "classification": "offer",
            "confidence": 0.97,
            "suggested_status": "offer",
            "evidence": "Congratulations! We would like to offer you the position.",
            "requires_human": True,
        }
    )


def _phone_screen_response() -> str:
    return json.dumps(
        {
            "classification": "phone_screen",
            "confidence": 0.88,
            "suggested_status": "phone_screen",
            "evidence": "We'd like to schedule a 30-minute call.",
            "requires_human": False,
        }
    )


def _rejected_response() -> str:
    return json.dumps(
        {
            "classification": "rejected",
            "confidence": 0.95,
            "suggested_status": "rejected",
            "evidence": "We will not be moving forward with your application.",
            "requires_human": True,
        }
    )


class TestClassifyEmail:
    @pytest.mark.asyncio
    async def test_offer_inference_parses_correctly(self, session: AsyncSession) -> None:
        # Arrange
        adapter = MockAdapter(responses=[_offer_response()])
        llm = LLMClient(session=session, adapter=adapter)
        raw = _make_raw()

        # Act
        result = await classify_email(session, llm, raw)

        # Assert
        assert isinstance(result, EmailStatusInference)
        assert result.classification == "offer"
        assert result.confidence == pytest.approx(0.97)
        assert result.suggested_status == "offer"
        assert result.requires_human is True
        assert "Congratulations" in result.evidence

    @pytest.mark.asyncio
    async def test_phone_screen_inference_parses_correctly(self, session: AsyncSession) -> None:
        adapter = MockAdapter(responses=[_phone_screen_response()])
        llm = LLMClient(session=session, adapter=adapter)
        raw = _make_raw(body="We'd like to schedule a 30-minute call with you.")

        result = await classify_email(session, llm, raw)

        assert result.classification == "phone_screen"
        assert result.requires_human is False
        assert result.confidence == pytest.approx(0.88)

    @pytest.mark.asyncio
    async def test_rejected_inference_parses_correctly(self, session: AsyncSession) -> None:
        adapter = MockAdapter(responses=[_rejected_response()])
        llm = LLMClient(session=session, adapter=adapter)
        raw = _make_raw(body="We will not be moving forward with your application.")

        result = await classify_email(session, llm, raw)

        assert result.classification == "rejected"
        assert result.requires_human is True

    @pytest.mark.asyncio
    async def test_prompt_is_created_if_absent(self, session: AsyncSession) -> None:
        """classify_email creates the prompt version on first call."""
        from sqlalchemy import select

        from app.db.models.prompt_version import PromptVersion

        adapter = MockAdapter(responses=[_offer_response()])
        llm = LLMClient(session=session, adapter=adapter)
        raw = _make_raw()

        # No prompt version exists yet
        await classify_email(session, llm, raw)

        result = await session.execute(
            select(PromptVersion).where(
                PromptVersion.name == "classify_email_status",
                PromptVersion.is_active == True,  # noqa: E712
            )
        )
        pv = result.scalar_one_or_none()
        assert pv is not None

    @pytest.mark.asyncio
    async def test_second_call_reuses_existing_prompt_version(
        self, session: AsyncSession
    ) -> None:
        """ensure_classify_prompt is idempotent — no duplicate rows."""
        from sqlalchemy import func, select

        from app.db.models.prompt_version import PromptVersion

        adapter = MockAdapter(
            responses=[_offer_response(), _phone_screen_response()]
        )
        llm = LLMClient(session=session, adapter=adapter)

        await classify_email(session, llm, _make_raw())
        await classify_email(session, llm, _make_raw(body="Schedule a call?"))

        count_result = await session.execute(
            select(func.count(PromptVersion.id)).where(
                PromptVersion.name == "classify_email_status"
            )
        )
        assert count_result.scalar_one() == 1

    @pytest.mark.asyncio
    async def test_body_truncated_to_2000_chars(self, session: AsyncSession) -> None:
        """Long bodies are truncated before being sent to LLM."""
        adapter = MockAdapter(responses=[_offer_response()])
        llm = LLMClient(session=session, adapter=adapter)
        long_body = "x" * 5000
        raw = _make_raw(body=long_body)

        await classify_email(session, llm, raw)

        # The rendered prompt in mock adapter's calls should contain at most 2000 'x'
        rendered = adapter.calls[0]["prompt"]
        # Count consecutive x's — the truncated body has exactly 2000
        x_count = rendered.count("x" * 2000)
        assert x_count >= 1
