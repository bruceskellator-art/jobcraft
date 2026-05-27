from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VectorPoint:
    """A point to be stored in the vector store."""

    id: str
    vector: list[float]
    payload: dict


@dataclass(frozen=True)
class ScoredPoint:
    """A search result from the vector store."""

    id: str
    score: float
    payload: dict


class VectorStore(Protocol):
    """Protocol all vector store implementations must satisfy."""

    async def ensure_collection(self, name: str, dim: int) -> None:
        """Create the collection if it does not exist. Idempotent."""
        ...

    async def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        """Insert or replace points in a collection."""
        ...

    async def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int,
        payload_filter: dict | None = None,
    ) -> list[ScoredPoint]:
        """Return up to top_k nearest neighbours, optionally filtered by payload."""
        ...

    async def get_vectors_by_payload(
        self,
        collection: str,
        payload_filter: dict,
    ) -> list[list[float]]:
        """Return all stored vectors whose payload matches the filter, unranked."""
        ...
