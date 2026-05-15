from __future__ import annotations

import logging
import os

from openai import AsyncOpenAI

from app.llm.adapters.base import AdapterResult

logger = logging.getLogger(__name__)


class OpenAIAdapter:
    """Calls OpenAI's Chat Completions API. Reads OPENAI_API_KEY from env."""

    def __init__(self) -> None:
        api_key = os.environ["OPENAI_API_KEY"]
        self._client = AsyncOpenAI(api_key=api_key)

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
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if force_json:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)

        choice = response.choices[0] if response.choices else None
        text = choice.message.content or "" if choice else ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else None
        output_tokens = usage.completion_tokens if usage else None

        return AdapterResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
