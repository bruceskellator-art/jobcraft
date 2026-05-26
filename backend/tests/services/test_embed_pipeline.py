from __future__ import annotations

import uuid

from app.db.models.experience_item import ExperienceItem
from app.db.models.job_posting import JobPosting
from app.embeddings.fake import FakeEmbeddingAdapter
from app.services.embed_pipeline import (
    COLLECTION_JOB_POSTINGS,
    COLLECTION_USER_EXPERIENCE,
    index_job,
    index_user_experience,
)
from app.vectorstore.memory import InMemoryVectorStore


def _make_job(extracted: dict | None = None) -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        source="test",
        source_url="https://example.com/job/1",
        source_id="job-1",
        company="Acme Corp",
        title="Senior Python Engineer",
        raw_content="We need a Python expert with ML experience.",
        extracted=extracted,
    )


class TestIndexUserExperience:
    async def test_populates_n_points_with_correct_payload(self, session) -> None:
        # Arrange
        from app.db.models.user import User

        user = User(id=uuid.uuid4(), email="u@test.com", name="Test User")
        session.add(user)

        items = [
            ExperienceItem(
                id=uuid.uuid4(),
                user_id=user.id,
                kind="work",
                content=f"Worked on Python project {i}",
            )
            for i in range(3)
        ]
        for item in items:
            session.add(item)
        await session.flush()

        embed = FakeEmbeddingAdapter(dim=32)
        store = InMemoryVectorStore()

        # Act
        await index_user_experience(session, embed, store, user.id)

        # Assert — 3 points in collection
        results = await store.search(
            COLLECTION_USER_EXPERIENCE,
            [1.0] * 32,
            top_k=10,
            payload_filter={"user_id": str(user.id)},
        )
        assert len(results) == 3
        for r in results:
            assert r.payload["user_id"] == str(user.id)
            assert "experience_id" in r.payload
            assert "kind" in r.payload

    async def test_no_items_does_not_raise(self, session) -> None:
        # Arrange
        user_id = uuid.uuid4()
        embed = FakeEmbeddingAdapter(dim=32)
        store = InMemoryVectorStore()

        # Act — should not raise, just log and return
        await index_user_experience(session, embed, store, user_id)

        # Assert — collection not even created (no ensure_collection call)
        results = await store.search(
            COLLECTION_USER_EXPERIENCE, [0.0] * 32, top_k=10
        )
        assert results == []


class TestIndexJob:
    async def test_upserts_point_with_correct_payload(self, session) -> None:
        # Arrange
        job = _make_job()
        embed = FakeEmbeddingAdapter(dim=32)
        store = InMemoryVectorStore()

        # Act
        await index_job(embed, store, job)

        # Assert
        results = await store.search(
            COLLECTION_JOB_POSTINGS,
            [1.0] * 32,
            top_k=1,
            payload_filter={"job_id": str(job.id)},
        )
        assert len(results) == 1
        assert results[0].payload["job_id"] == str(job.id)
        assert results[0].payload["company"] == "Acme Corp"

    async def test_uses_extracted_when_present(self, session) -> None:
        # Arrange — job with extracted dict
        extracted = {
            "summary": "ML infrastructure role using PyTorch and Kubernetes.",
            "required_skills": ["PyTorch", "Kubernetes", "Python"],
        }
        job_with = _make_job(extracted=extracted)
        job_without = _make_job(extracted=None)

        embed = FakeEmbeddingAdapter(dim=512)
        store = InMemoryVectorStore()

        # Act
        await index_job(embed, store, job_with)
        await index_job(embed, store, job_without)

        # Assert — both indexed successfully with correct payloads
        r_with = await store.search(
            COLLECTION_JOB_POSTINGS, [1.0] * 512, top_k=10,
            payload_filter={"job_id": str(job_with.id)},
        )
        r_without = await store.search(
            COLLECTION_JOB_POSTINGS, [1.0] * 512, top_k=10,
            payload_filter={"job_id": str(job_without.id)},
        )
        assert len(r_with) == 1
        assert len(r_without) == 1
