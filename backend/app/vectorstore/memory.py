from __future__ import annotations

import math

from app.vectorstore.base import ScoredPoint, VectorPoint


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _matches_filter(payload: dict, payload_filter: dict) -> bool:
    return all(payload.get(k) == v for k, v in payload_filter.items())


class InMemoryVectorStore:
    """Pure-Python vector store for tests and local dev.

    Stores all points in memory; no external dependencies required.
    """

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, VectorPoint]] = {}

    async def ensure_collection(self, name: str, dim: int) -> None:
        """Create the collection if it does not exist. Idempotent."""
        if name not in self._collections:
            self._collections[name] = {}

    async def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        """Insert or replace points by id."""
        store = self._collections.setdefault(collection, {})
        for point in points:
            store[point.id] = point

    async def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int,
        payload_filter: dict | None = None,
    ) -> list[ScoredPoint]:
        """Return up to top_k nearest neighbours sorted by descending cosine score."""
        store = self._collections.get(collection, {})
        candidates: list[tuple[float, VectorPoint]] = []
        for point in store.values():
            if payload_filter is not None and not _matches_filter(
                point.payload, payload_filter
            ):
                continue
            score = _cosine(vector, point.vector)
            candidates.append((score, point))

        candidates.sort(key=lambda t: t[0], reverse=True)
        return [
            ScoredPoint(id=p.id, score=s, payload=p.payload)
            for s, p in candidates[:top_k]
        ]
