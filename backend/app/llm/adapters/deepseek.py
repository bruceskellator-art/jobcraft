from __future__ import annotations

import logging
import os

from openai import AsyncOpenAI

from app.llm.adapters.base import AdapterResult

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
# Default model — always used regardless of the prompt_version.model field,
# since existing prompt versions carry Anthropic model names.
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"

_JSON_INSTRUCTION = (
    "\n\nRespond with valid JSON only. Do not include any prose outside the JSON object."
)


class DeepSeekAdapter:
    """Calls DeepSeek's OpenAI-compatible Chat Completions API.

    Reads DEEPSEEK_API_KEY from the environment.

    DeepSeek model names differ from Anthropic/OpenAI, so the ``model``
    argument passed by LLMClient (sourced from prompt_version.model) is
    ignored in favour of the adapter-level ``model`` setting.
    """

    def __init__(self, model: str = DEEPSEEK_DEFAULT_MODEL) -> None:
        api_key = os.environ["DEEPSEEK_API_KEY"]
        self._client = AsyncOpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        self._model = model

    async def generate(
        self,
        *,
        model: str,  # noqa: ARG002 — ignored; DeepSeek uses self._model
        system: str | None,
        prompt: str,
        temperature: float,
        max_tokens: int,
        force_json: bool,
    ) -> AdapterResult:
        messages: list[dict] = []

        effective_system = system or ""
        if force_json:
            effective_system = (effective_system + _JSON_INSTRUCTION).strip()

        if effective_system:
            messages.append({"role": "system", "content": effective_system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": self._model,
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
