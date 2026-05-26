from __future__ import annotations

from typing import Protocol


class EmbeddingClient(Protocol):
    """Protocol that all embedding adapters must satisfy."""

    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns one float vector per input text."""
        ...
