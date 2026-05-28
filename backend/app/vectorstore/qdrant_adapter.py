from __future__ import annotations

import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.vectorstore.base import ScoredPoint, VectorPoint

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    """Qdrant-backed vector store using the async client."""

    def __init__(self, url: str) -> None:
        self._client = AsyncQdrantClient(url=url)

    async def ensure_collection(self, name: str, dim: int) -> None:
        """Create a COSINE-distance collection if it does not already exist."""
        existing = await self._client.get_collections()
        names = {c.name for c in existing.collections}
        if name in names:
            return

        await self._client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(
                size=dim,
                distance=qmodels.Distance.COSINE,
            ),
        )
        logger.info("Created Qdrant collection %r (dim=%d, COSINE)", name, dim)

    async def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        """Upsert points into the named collection."""
        structs = [
            qmodels.PointStruct(
                id=p.id,
                vector=p.vector,
                payload=p.payload,
            )
            for p in points
        ]
        await self._client.upsert(collection_name=collection, points=structs)

    async def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int,
        payload_filter: dict | None = None,
    ) -> list[ScoredPoint]:
        """Return top_k nearest neighbours, optionally filtered by payload."""
        qdrant_filter: qmodels.Filter | None = None
        if payload_filter:
            conditions: list[qmodels.FieldCondition] = [
                qmodels.FieldCondition(
                    key=k,
                    match=qmodels.MatchValue(value=v),
                )
                for k, v in payload_filter.items()
            ]
            qdrant_filter = qmodels.Filter(must=conditions)  # type: ignore[arg-type]

        results = await self._client.query_points(
            collection_name=collection,
            query=vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )
        return [
            ScoredPoint(
                id=str(r.id),
                score=r.score,
                payload=dict(r.payload or {}),
            )
            for r in results.points
        ]

    # Maximum number of points fetched per scroll call when retrieving all
    # vectors matching a filter. Large enough to cover typical user corpora in
    # one round-trip without unbounded memory use.
    _SCROLL_LIMIT = 1000

    async def get_vectors_by_payload(
        self,
        collection: str,
        payload_filter: dict,
    ) -> list[list[float]]:
        """Return all stored vectors whose payload matches the filter, unranked.

        Uses scroll (with_vectors=True) and paginates until exhausted.
        """
        conditions: list[qmodels.FieldCondition] = [
            qmodels.FieldCondition(key=k, match=qmodels.MatchValue(value=v))
            for k, v in payload_filter.items()
        ]
        qdrant_filter = qmodels.Filter(must=conditions)  # type: ignore[arg-type]

        vectors: list[list[float]] = []
        offset = None
        while True:
            scroll_result, next_offset = await self._client.scroll(
                collection_name=collection,
                scroll_filter=qdrant_filter,
                with_vectors=True,
                limit=self._SCROLL_LIMIT,
                offset=offset,
            )
            for point in scroll_result:
                raw = point.vector
                if raw is not None and isinstance(raw, list) and raw and isinstance(raw[0], float):
                    vectors.append(raw)
            if next_offset is None:
                break
            offset = next_offset
        return vectors

    async def aclose(self) -> None:
        """Close the underlying Qdrant async client."""
        await self._client.close()

    async def __aenter__(self) -> QdrantVectorStore:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
