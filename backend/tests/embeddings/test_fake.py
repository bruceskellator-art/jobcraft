from __future__ import annotations

import math

from app.embeddings.fake import FakeEmbeddingAdapter


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


class TestFakeEmbeddingAdapter:
    async def test_deterministic_same_input_same_vector(self) -> None:
        # Arrange
        adapter = FakeEmbeddingAdapter(dim=64)
        text = "python machine learning engineer"

        # Act
        v1 = (await adapter.embed([text]))[0]
        v2 = (await adapter.embed([text]))[0]

        # Assert
        assert v1 == v2

    async def test_shared_words_higher_cosine_than_disjoint(self) -> None:
        # Arrange — use large dim to minimise hash collisions
        adapter = FakeEmbeddingAdapter(dim=512)
        text_a = "python machine learning"
        text_b = "python web development"   # shares "python" with text_a
        text_c = "java enterprise architecture"  # disjoint from text_a

        # Act
        vectors = await adapter.embed([text_a, text_b, text_c])
        va, vb, vc = vectors

        sim_ab = _cosine(va, vb)
        sim_ac = _cosine(va, vc)

        # Assert — overlapping pair scores higher than disjoint pair
        assert sim_ab > sim_ac

    async def test_correct_dim(self) -> None:
        # Arrange
        adapter = FakeEmbeddingAdapter(dim=32)

        # Act
        vectors = await adapter.embed(["hello world"])

        # Assert
        assert len(vectors[0]) == 32

    async def test_vector_is_l2_normalized(self) -> None:
        # Arrange
        adapter = FakeEmbeddingAdapter(dim=64)

        # Act
        vector = (await adapter.embed(["data science python tensorflow"]))[0]
        magnitude = math.sqrt(sum(v * v for v in vector))

        # Assert — should be within float rounding of 1.0
        assert abs(magnitude - 1.0) < 1e-9

    async def test_empty_text_returns_uniform_normalized_vector(self) -> None:
        # Arrange
        adapter = FakeEmbeddingAdapter(dim=16)

        # Act
        vector = (await adapter.embed([""]))[0]
        magnitude = math.sqrt(sum(v * v for v in vector))

        # Assert — uniform, still unit-length
        assert len(vector) == 16
        assert abs(magnitude - 1.0) < 1e-9
        expected = 1.0 / math.sqrt(16)
        assert all(abs(v - expected) < 1e-9 for v in vector)
