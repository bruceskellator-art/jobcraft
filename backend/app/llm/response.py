from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class LLMResponse(Generic[T]):  # noqa: UP046
    """Typed result returned by LLMClient.complete()."""

    parsed: T | None
    raw: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    cost_usd: Decimal | None
    call_id: uuid.UUID
