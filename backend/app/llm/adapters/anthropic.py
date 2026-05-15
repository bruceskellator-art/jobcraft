from __future__ import annotations

import logging
import os

from anthropic import AsyncAnthropic

from app.llm.adapters.base import AdapterResult

logger = logging.getLogger(__name__)

_JSON_INSTRUCTION = (
    "\n\nRespond with valid JSON only. Do not include any prose outside the JSON object."
)


class AnthropicAdapter:
    """Calls Anthropic's Messages API. Reads ANTHROPIC_API_KEY from env."""

    def __init__(self) -> None:
        api_key = os.environ["ANTHROPIC_API_KEY"]
        self._client = AsyncAnthropic(api_key=api_key)

    async def generate(
        self,
        *,
        model: str,
        system: str | None,
        prompt: str,
        temperature: float,
        max_tokens: int,
        force_json: bool,
    ) -> AdapterResult:
        effective_system = system or ""
        effective_prompt = prompt

        if force_json:
            effective_system = (effective_system + _JSON_INSTRUCTION).strip()

        messages = [{"role": "user", "content": effective_prompt}]

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if effective_system:
            kwargs["system"] = effective_system

        response = await self._client.messages.create(**kwargs)

        text = response.content[0].text if response.content else ""
        input_tokens = response.usage.input_tokens if response.usage else None
        output_tokens = response.usage.output_tokens if response.usage else None

        return AdapterResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
