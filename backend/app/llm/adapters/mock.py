from __future__ import annotations

import logging
from collections.abc import Callable

from app.llm.adapters.base import AdapterResult

logger = logging.getLogger(__name__)

_TOKENS_PER_CHAR = 4  # rough approximation: 1 token ≈ 4 chars


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _TOKENS_PER_CHAR)


class MockAdapter:
    """
    Test adapter — no network calls.

    Pass either:
    - responses: list[str]  — popped in order (index 0 first)
    - fn: Callable[[str], str]  — called with the rendered prompt each time
    """

    def __init__(
        self,
        responses: list[str] | None = None,
        fn: Callable[[str], str] | None = None,
    ) -> None:
        if responses is None and fn is None:
            raise ValueError("Provide either responses or fn")
        self._responses = list(responses) if responses is not None else None
        self._fn = fn
        self.calls: list[dict] = []  # records every invocation for assertions

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
        if self._fn is not None:
            text = self._fn(prompt)
        elif self._responses:
            text = self._responses.pop(0)
        else:
            raise RuntimeError("MockAdapter ran out of canned responses")

        self.calls.append(
            {
                "model": model,
                "system": system,
                "prompt": prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "force_json": force_json,
                "response": text,
            }
        )

        return AdapterResult(
            text=text,
            input_tokens=_estimate_tokens(prompt),
            output_tokens=_estimate_tokens(text),
        )
