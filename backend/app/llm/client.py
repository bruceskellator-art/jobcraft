from __future__ import annotations

import logging
import time
import uuid
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.llm_call import LlmCall
from app.db.models.prompt_version import PromptVersion
from app.llm.adapters.base import LLMAdapter
from app.llm.errors import LLMError
from app.llm.pricing import estimate_cost
from app.llm.render import render_template
from app.llm.response import LLMResponse

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_SYSTEM: str | None = None
_MAX_ALLOWED_TOKENS = 8192


class LLMClient:
    """Single point of LLM access. Logs every call to llm_calls table."""

    def __init__(self, session: AsyncSession, adapter: LLMAdapter) -> None:
        self._session = session
        self._adapter = adapter

    async def complete(
        self,
        prompt_version_id: uuid.UUID,
        inputs: dict,
        response_model: type[T] | None = None,
    ) -> LLMResponse[T]:
        # --- a. Load PromptVersion ---
        result = await self._session.execute(
            select(PromptVersion).where(PromptVersion.id == prompt_version_id)
        )
        pv = result.scalar_one_or_none()
        if pv is None:
            raise LLMError(f"unknown prompt_version: {prompt_version_id}")

        # --- b. Render template ---
        rendered = render_template(pv.template, inputs)

        metadata = pv.metadata_ or {}
        max_tokens: int = min(
            int(metadata.get("max_tokens", _DEFAULT_MAX_TOKENS)),
            _MAX_ALLOWED_TOKENS,
        )
        system: str | None = metadata.get("system", _DEFAULT_SYSTEM)
        force_json: bool = response_model is not None

        # --- c. Call adapter, measure latency ---
        start = time.monotonic()
        adapter_error: Exception | None = None
        adapter_result = None
        try:
            adapter_result = await self._adapter.generate(
                model=pv.model,
                system=system,
                prompt=rendered,
                temperature=pv.temperature,
                max_tokens=max_tokens,
                force_json=force_json,
            )
        except Exception as exc:
            adapter_error = exc

        latency_ms = int((time.monotonic() - start) * 1000)

        # --- d. Parse structured response ---
        parsed: T | None = None
        parse_error: str | None = None

        if adapter_error is not None:
            parse_error = str(adapter_error)
        elif response_model is not None and adapter_result is not None:
            try:
                parsed = response_model.model_validate_json(adapter_result.text)
            except Exception as exc:
                parse_error = f"parse error: {exc}"

        # --- e. Compute cost and write LlmCall row ---
        raw_text = adapter_result.text if adapter_result is not None else ""
        input_tokens = adapter_result.input_tokens if adapter_result is not None else None
        output_tokens = adapter_result.output_tokens if adapter_result is not None else None
        cost = estimate_cost(pv.model, input_tokens, output_tokens)

        parsed_dict: dict | None = None
        if parsed is not None:
            try:
                parsed_dict = parsed.model_dump()
            except Exception as exc:
                logger.exception("Failed to serialize parsed response to dict: %s", exc)
                parsed_dict = None

        call = LlmCall(
            id=uuid.uuid4(),
            prompt_version_id=pv.id,
            inputs=inputs,
            rendered_prompt=rendered,
            response=raw_text,
            parsed_response=parsed_dict,
            model=pv.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            error=parse_error,
        )
        self._session.add(call)
        await self._session.flush()

        # --- raise after persisting ---
        if adapter_error is not None:
            raise LLMError(
                f"adapter error: {adapter_error}", cause=adapter_error
            ) from adapter_error
        if parse_error is not None:
            raise LLMError(parse_error)

        return LLMResponse(
            parsed=parsed,
            raw=raw_text,
            model=pv.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            call_id=call.id,
        )
