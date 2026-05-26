from __future__ import annotations

import math
import re


class FakeEmbeddingAdapter:
    """Deterministic bag-of-words embedding adapter for tests and local dev.

    Each text is embedded by:
    1. Lowercasing and splitting on non-alphanumeric characters.
    2. Hashing each token into a bucket in [0, dim).
    3. L2-normalising the resulting count vector.

    This guarantees texts sharing tokens have higher cosine similarity than
    texts with disjoint tokens, without any randomness or network calls.
    """

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def _embed_one(self, text: str) -> list[float]:
        tokens = [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]
        counts = [0.0] * self.dim
        for token in tokens:
            bucket = hash(token) % self.dim
            counts[bucket] += 1.0

        magnitude = math.sqrt(sum(c * c for c in counts))
        if magnitude == 0.0:
            uniform = 1.0 / math.sqrt(self.dim)
            return [uniform] * self.dim

        return [c / magnitude for c in counts]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed each text deterministically. No I/O, no randomness."""
        return [self._embed_one(t) for t in texts]
