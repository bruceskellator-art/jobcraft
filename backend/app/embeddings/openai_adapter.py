from __future__ import annotations

import logging
import os

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100


class OpenAIEmbeddingAdapter:
    """Embedding adapter backed by OpenAI text-embedding-3-small.

    Reads OPENAI_API_KEY from the environment at construction time so the
    missing-key error surfaces early, not mid-request.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dim: int = 1536,
    ) -> None:
        api_key = os.environ["OPENAI_API_KEY"]
        self._client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in batches. Returns one float vector per input."""
        if not texts:
            return []

        results: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            logger.debug("Embedding batch %d texts with %s", len(batch), self.model)
            response = await self._client.embeddings.create(
                model=self.model,
                input=batch,
            )
            for item in response.data:
                results.append(item.embedding)

        return results
