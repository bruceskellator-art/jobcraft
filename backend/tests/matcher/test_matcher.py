from __future__ import annotations

import json
import uuid

from app.db.models.experience_item import ExperienceItem
from app.db.models.job_posting import JobPosting
from app.db.models.user import User
from app.embeddings.fake import FakeEmbeddingAdapter
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.matcher.service import compute_match, prefilter_score
from app.vectorstore.memory import InMemoryVectorStore

_MATCH_RESULT_DICT = {
    "overall_score": 0.85,
    "dimension_scores": {
        "skills": 0.9,
        "seniority": 0.8,
        "domain": 0.85,
        "culture": 0.85,
    },
    "gaps": [
        {
            "skill": "kubernetes",
            "severity": "high",
            "rationale": "Not mentioned in experience.",
        }
    ],
    "rationale": "Strong Python and ML alignment. Gap in DevOps tooling.",
    "matched_experiences": [],
}
_MATCH_RESULT_JSON = json.dumps(_MATCH_RESULT_DICT)


def _make_job(title: str = "Senior Python ML Engineer") -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        source="test",
        source_url="https://example.com/job/1",
        source_id=str(uuid.uuid4()),
        company="ML Corp",
        title=title,
        raw_content=f"{title}. Python, machine learning, PyTorch required.",
        extracted=None,
    )


async def _seed_user_with_items(session, n: int = 2) -> tuple[User, list[ExperienceItem]]:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", name="Test User")
    session.add(user)
    items = [
        ExperienceItem(
            id=uuid.uuid4(),
            user_id=user.id,
            kind="work",
            content="Built Python machine learning pipelines using PyTorch and pandas.",
        )
        for _ in range(n)
    ]
    for item in items:
        session.add(item)
    await session.flush()
    return user, items


class TestPrefilterScore:
    async def test_score_in_range(self, session) -> None:
        # Arrange
        user, _ = await _seed_user_with_items(session)
        job = _make_job()
        embed = FakeEmbeddingAdapter(dim=128)

        # Act
        score = await prefilter_score(session, embed, user.id, job)

        # Assert
        assert -1.0 <= score <= 1.0

    async def test_higher_score_for_overlapping_jd(self, session) -> None:
        # Arrange — experience is Python ML; compare matching vs non-matching JD
        user, _ = await _seed_user_with_items(session)
        job_match = _make_job("Python Machine Learning Engineer")
        job_miss = JobPosting(
            id=uuid.uuid4(),
            source="test",
            source_url="https://example.com/job/2",
            source_id=str(uuid.uuid4()),
            company="Corp",
            title="Java Enterprise Developer",
            raw_content="Java enterprise architecture, Spring Boot, Oracle DB.",
            extracted=None,
        )
        embed = FakeEmbeddingAdapter(dim=512)

        # Act
        score_match = await prefilter_score(session, embed, user.id, job_match)
        score_miss = await prefilter_score(session, embed, user.id, job_miss)

        # Assert — overlapping JD scores higher
        assert score_match > score_miss

    async def test_returns_zero_when_no_experience(self, session) -> None:
        # Arrange
        user_id = uuid.uuid4()
        job = _make_job()
        embed = FakeEmbeddingAdapter(dim=64)

        # Act
        score = await prefilter_score(session, embed, user_id, job)

        # Assert
        assert score == 0.0


class TestComputeMatch:
    async def test_persists_match_with_correct_fields(self, session) -> None:
        # Arrange
        user, _ = await _seed_user_with_items(session)
        job = _make_job()
        session.add(job)
        await session.flush()

        embed = FakeEmbeddingAdapter(dim=128)
        store = InMemoryVectorStore()
        adapter = MockAdapter(responses=[_MATCH_RESULT_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        match = await compute_match(session, llm, embed, store, user.id, job)
        await session.commit()

        # Assert
        assert match.user_id == user.id
        assert match.job_id == job.id
        assert abs(match.overall_score - 0.85) < 1e-6
        assert match.dimension_scores["skills"] == 0.9
        assert isinstance(match.gaps, list)
        assert len(match.gaps) == 1
        assert match.gaps[0]["skill"] == "kubernetes"
        assert match.rationale == _MATCH_RESULT_DICT["rationale"]

    async def test_compute_match_idempotent_no_duplicate(self, session) -> None:
        # Arrange
        user, _ = await _seed_user_with_items(session)
        job = _make_job()
        session.add(job)
        await session.flush()

        embed = FakeEmbeddingAdapter(dim=128)
        store = InMemoryVectorStore()

        # First call
        adapter1 = MockAdapter(responses=[_MATCH_RESULT_JSON])
        llm1 = LLMClient(session=session, adapter=adapter1)
        m1 = await compute_match(session, llm1, embed, store, user.id, job)
        await session.commit()

        # Second call — same user+job, different score in mock response
        updated = dict(_MATCH_RESULT_DICT)
        updated["overall_score"] = 0.75
        adapter2 = MockAdapter(responses=[json.dumps(updated)])
        llm2 = LLMClient(session=session, adapter=adapter2)
        m2 = await compute_match(session, llm2, embed, store, user.id, job)
        await session.commit()

        # Assert — same row id (update, not insert), updated score
        assert m1.id == m2.id
        assert abs(m2.overall_score - 0.75) < 1e-6
