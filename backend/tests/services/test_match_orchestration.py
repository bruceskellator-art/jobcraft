"""Tests for match_orchestration service.

Uses FakeEmbeddingAdapter + InMemoryVectorStore + MockAdapter to avoid
any network or database dependencies beyond the in-memory SQLite session.
"""

from __future__ import annotations

import json
import uuid

from app.db.models.experience_item import ExperienceItem
from app.db.models.job_posting import JobPosting
from app.db.models.match import Match
from app.db.models.user import User
from app.embeddings.fake import FakeEmbeddingAdapter
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.services.match_orchestration import match_all_jobs, match_job
from app.vectorstore.memory import InMemoryVectorStore

_MATCH_JSON = json.dumps(
    {
        "overall_score": 0.80,
        "dimension_scores": {"skills": 0.8, "seniority": 0.8, "domain": 0.8, "culture": 0.8},
        "gaps": [],
        "rationale": "Good fit.",
        "matched_experiences": [],
    }
)


def _make_job(title: str = "Python Engineer") -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        source="test",
        source_url="https://example.com/job/1",
        source_id=str(uuid.uuid4()),
        company="Acme",
        title=title,
        raw_content=f"{title}. Python required.",
        extracted=None,
    )


async def _seed(session, n_items: int = 2) -> tuple[User, list[ExperienceItem]]:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", name="Test")
    session.add(user)
    items = [
        ExperienceItem(
            id=uuid.uuid4(),
            user_id=user.id,
            kind="work",
            content="Python backend development.",
        )
        for _ in range(n_items)
    ]
    for item in items:
        session.add(item)
    await session.flush()
    return user, items


class TestMatchJob:
    async def test_match_job_persists_match(self, session) -> None:
        # Arrange
        user, _ = await _seed(session)
        job = _make_job()
        session.add(job)
        await session.flush()

        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        adapter = MockAdapter(responses=[_MATCH_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        match = await match_job(session, llm, embed, store, user.id, job)
        await session.commit()

        # Assert
        assert isinstance(match, Match)
        assert match.user_id == user.id
        assert match.job_id == job.id
        assert abs(match.overall_score - 0.80) < 1e-6

    async def test_match_job_idempotent(self, session) -> None:
        # Arrange
        user, _ = await _seed(session)
        job = _make_job()
        session.add(job)
        await session.flush()

        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()

        adapter1 = MockAdapter(responses=[_MATCH_JSON])
        llm1 = LLMClient(session=session, adapter=adapter1)
        m1 = await match_job(session, llm1, embed, store, user.id, job)
        await session.commit()

        updated = json.loads(_MATCH_JSON)
        updated["overall_score"] = 0.55
        adapter2 = MockAdapter(responses=[json.dumps(updated)])
        llm2 = LLMClient(session=session, adapter=adapter2)
        m2 = await match_job(session, llm2, embed, store, user.id, job)
        await session.commit()

        # Assert — same row updated, not a new insert
        assert m1.id == m2.id
        assert abs(m2.overall_score - 0.55) < 1e-6


class TestMatchAllJobs:
    async def test_match_all_jobs_returns_correct_count(self, session) -> None:
        # Arrange — seed two jobs
        user, _ = await _seed(session)
        jobs = [_make_job(f"Job {i}") for i in range(3)]
        for job in jobs:
            session.add(job)
        await session.flush()

        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        # Provide one response per job
        responses = [_MATCH_JSON] * 3
        adapter = MockAdapter(responses=responses)
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        count = await match_all_jobs(session, llm, embed, store, user.id, limit=10)
        await session.commit()

        # Assert
        assert count == 3

    async def test_match_all_jobs_isolates_failing_job(self, session) -> None:
        # Arrange — two jobs; first LLM call raises, second succeeds
        user, _ = await _seed(session)
        jobs = [_make_job(f"Job {i}") for i in range(2)]
        for job in jobs:
            session.add(job)
        await session.flush()

        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()

        # MockAdapter with responses — first response is invalid JSON to force failure
        adapter = MockAdapter(responses=["NOT_VALID_JSON", _MATCH_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        # Act — should not raise; one failure is isolated
        count = await match_all_jobs(session, llm, embed, store, user.id, limit=10)
        await session.commit()

        # Assert — one succeeded, one failed and was skipped
        assert count == 1

    async def test_match_all_jobs_returns_zero_when_no_jobs(self, session) -> None:
        # Arrange — no jobs seeded
        user, _ = await _seed(session)
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        count = await match_all_jobs(session, llm, embed, store, user.id)

        # Assert
        assert count == 0
