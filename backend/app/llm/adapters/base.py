from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AdapterResult:
    """Raw output from an LLM provider adapter."""

    text: str
    input_tokens: int | None
    output_tokens: int | None


class LLMAdapter(Protocol):
    """Protocol all provider adapters must satisfy."""

    async def generate(
        self,
        *,
        model: str,
        system: str | None,
        prompt: str,
        temperature: float,
        max_tokens: int,
        force_json: bool,
    ) -> AdapterResult: ...
