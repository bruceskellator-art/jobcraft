from __future__ import annotations

import json
import uuid

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from app.db.models.llm_call import LlmCall
from app.db.models.prompt_version import PromptVersion
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.llm.errors import LLMError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prompt_version(**overrides) -> PromptVersion:
    defaults = dict(
        id=uuid.uuid4(),
        name="test_prompt",
        version=1,
        template="Extract from: {{ text }}",
        model="claude-3-5-haiku-20241022",
        temperature=0.0,
        metadata_={},
        is_active=True,
    )
    defaults.update(overrides)
    return PromptVersion(**defaults)


async def _seed(session, pv: PromptVersion) -> PromptVersion:
    session.add(pv)
    await session.flush()
    return pv


async def _count_llm_calls(session) -> int:
    result = await session.execute(select(LlmCall))
    return len(result.scalars().all())


# ---------------------------------------------------------------------------
# Test 1: plain complete (no response_model) writes one llm_calls row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_no_response_model_returns_raw_and_writes_row(session):
    # Arrange
    pv = await _seed(session, _make_prompt_version())
    mock = MockAdapter(responses=["hello world"])
    client = LLMClient(session=session, adapter=mock)

    # Act
    response = await client.complete(pv.id, inputs={"text": "some resume"})

    # Assert — LLMResponse fields
    assert response.raw == "hello world"
    assert response.parsed is None
    assert response.model == pv.model
    assert response.input_tokens is not None
    assert response.output_tokens is not None
    assert response.latency_ms >= 0
    assert isinstance(response.call_id, uuid.UUID)

    # Assert — exactly one row written
    assert await _count_llm_calls(session) == 1
    row_result = await session.execute(select(LlmCall).where(LlmCall.id == response.call_id))
    row = row_result.scalar_one()
    assert row.response == "hello world"
    assert row.input_tokens is not None
    assert row.output_tokens is not None
    assert row.error is None


# ---------------------------------------------------------------------------
# Test 2: complete with response_model parses structured JSON
# ---------------------------------------------------------------------------

class _Extracted(BaseModel):
    name: str
    years: int


@pytest.mark.asyncio
async def test_complete_with_response_model_parses_json(session):
    # Arrange
    payload = json.dumps({"name": "Alice", "years": 5})
    pv = await _seed(session, _make_prompt_version(name="extract_prompt", version=2))
    mock = MockAdapter(responses=[payload])
    client = LLMClient(session=session, adapter=mock)

    # Act
    response = await client.complete(
        pv.id, inputs={"text": "Alice 5 years"}, response_model=_Extracted
    )

    # Assert — parsed object
    assert isinstance(response.parsed, _Extracted)
    assert response.parsed.name == "Alice"
    assert response.parsed.years == 5
    assert response.raw == payload

    # Assert — row persisted with parsed_response dict
    row_result = await session.execute(select(LlmCall).where(LlmCall.id == response.call_id))
    row = row_result.scalar_one()
    assert row.parsed_response == {"name": "Alice", "years": 5}
    assert row.error is None


# ---------------------------------------------------------------------------
# Test 3: StrictUndefined raises when a template variable is missing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_template_variable_raises(session):
    # Arrange
    pv = await _seed(session, _make_prompt_version(name="strict_prompt", version=3))
    mock = MockAdapter(responses=["irrelevant"])
    client = LLMClient(session=session, adapter=mock)

    # Act / Assert — jinja2.UndefinedError propagates before adapter is called
    with pytest.raises(Exception) as exc_info:
        await client.complete(pv.id, inputs={})  # "text" var missing

    assert "text" in str(exc_info.value).lower() or "undefined" in str(exc_info.value).lower()
    # Adapter must NOT have been called
    assert len(mock.calls) == 0


# ---------------------------------------------------------------------------
# Test 4: adapter error writes llm_calls row with error set, raises LLMError
# ---------------------------------------------------------------------------

class _BrokenAdapter:
    """Always raises — simulates a network/API failure."""

    async def generate(self, *, model, system, prompt, temperature, max_tokens, force_json):
        raise RuntimeError("connection refused")


@pytest.mark.asyncio
async def test_adapter_error_writes_row_and_raises_llm_error(session):
    # Arrange
    pv = await _seed(session, _make_prompt_version(name="error_prompt", version=4))
    client = LLMClient(session=session, adapter=_BrokenAdapter())  # type: ignore[arg-type]

    # Act / Assert
    with pytest.raises(LLMError) as exc_info:
        await client.complete(pv.id, inputs={"text": "anything"})

    assert "connection refused" in str(exc_info.value)

    # Row must exist with error field populated
    assert await _count_llm_calls(session) == 1
    row_result = await session.execute(select(LlmCall))
    row = row_result.scalars().first()
    assert row is not None
    assert row.error is not None
    assert "connection refused" in row.error
