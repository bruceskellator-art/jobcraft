from __future__ import annotations

from app.vectorstore.base import VectorPoint
from app.vectorstore.memory import InMemoryVectorStore


def _point(id: str, vector: list[float], payload: dict | None = None) -> VectorPoint:
    return VectorPoint(id=id, vector=vector, payload=payload or {})


class TestInMemoryVectorStore:
    async def test_upsert_and_search_returns_nearest_first(self) -> None:
        # Arrange
        store = InMemoryVectorStore()
        await store.ensure_collection("test", dim=3)
        await store.upsert(
            "test",
            [
                _point("a", [1.0, 0.0, 0.0]),
                _point("b", [0.0, 1.0, 0.0]),
                _point("c", [0.0, 0.0, 1.0]),
            ],
        )

        # Act — query closest to "a"
        results = await store.search("test", [1.0, 0.0, 0.0], top_k=3)

        # Assert — "a" is first
        assert results[0].id == "a"
        assert results[0].score > results[1].score

    async def test_payload_filter_narrows_results(self) -> None:
        # Arrange
        store = InMemoryVectorStore()
        await store.ensure_collection("col", dim=2)
        await store.upsert(
            "col",
            [
                _point("x1", [1.0, 0.0], {"kind": "work"}),
                _point("x2", [0.9, 0.1], {"kind": "education"}),
                _point("x3", [0.8, 0.2], {"kind": "work"}),
            ],
        )

        # Act — filter to kind=work only
        results = await store.search("col", [1.0, 0.0], top_k=10, payload_filter={"kind": "work"})

        # Assert — only work items returned
        assert len(results) == 2
        assert all(r.payload["kind"] == "work" for r in results)

    async def test_top_k_respected(self) -> None:
        # Arrange
        store = InMemoryVectorStore()
        await store.ensure_collection("col", dim=2)
        await store.upsert(
            "col",
            [_point(str(i), [float(i), 0.0]) for i in range(5)],
        )

        # Act
        results = await store.search("col", [4.0, 0.0], top_k=2)

        # Assert
        assert len(results) == 2

    async def test_upsert_replaces_existing_point(self) -> None:
        # Arrange
        store = InMemoryVectorStore()
        await store.ensure_collection("col", dim=2)
        await store.upsert("col", [_point("p", [1.0, 0.0], {"v": 1})])

        # Act — upsert same id with new vector/payload
        await store.upsert("col", [_point("p", [0.0, 1.0], {"v": 2})])
        results = await store.search("col", [0.0, 1.0], top_k=1)

        # Assert — updated payload
        assert results[0].id == "p"
        assert results[0].payload["v"] == 2

    async def test_ensure_collection_idempotent(self) -> None:
        # Arrange
        store = InMemoryVectorStore()

        # Act — call twice, should not raise
        await store.ensure_collection("col", dim=4)
        await store.ensure_collection("col", dim=4)

        # Assert — collection still usable
        await store.upsert("col", [_point("a", [1.0, 0.0, 0.0, 0.0])])
        results = await store.search("col", [1.0, 0.0, 0.0, 0.0], top_k=1)
        assert len(results) == 1

    async def test_get_vectors_by_payload_returns_matching_vectors(self) -> None:
        # Arrange
        store = InMemoryVectorStore()
        await store.ensure_collection("col", dim=2)
        await store.upsert(
            "col",
            [
                _point("u1a", [1.0, 0.0], {"user_id": "u1"}),
                _point("u1b", [0.5, 0.5], {"user_id": "u1"}),
                _point("u2a", [0.0, 1.0], {"user_id": "u2"}),
            ],
        )

        # Act — fetch vectors for u1 only
        vectors = await store.get_vectors_by_payload("col", {"user_id": "u1"})

        # Assert — exactly 2 vectors returned, both belonging to u1
        assert len(vectors) == 2
        assert [1.0, 0.0] in vectors
        assert [0.5, 0.5] in vectors

    async def test_get_vectors_by_payload_empty_when_no_match(self) -> None:
        # Arrange
        store = InMemoryVectorStore()
        await store.ensure_collection("col", dim=2)
        await store.upsert("col", [_point("a", [1.0, 0.0], {"user_id": "u1"})])

        # Act — filter for a user with no points
        vectors = await store.get_vectors_by_payload("col", {"user_id": "nobody"})

        # Assert
        assert vectors == []

    async def test_get_vectors_by_payload_empty_collection(self) -> None:
        # Arrange — collection doesn't even exist yet
        store = InMemoryVectorStore()

        # Act
        vectors = await store.get_vectors_by_payload("nonexistent", {"user_id": "u1"})

        # Assert — returns empty list, no error
        assert vectors == []
