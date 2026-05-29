"""Integration tests for app.services.generation orchestration.

Uses FakeEmbeddingAdapter + InMemoryVectorStore + MockAdapter (canned JSON).
No network, no typst binary required.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.db.models.artifact import Artifact
from app.db.models.experience_item import ExperienceItem
from app.db.models.job_posting import JobPosting
from app.db.models.user import User
from app.embeddings.fake import FakeEmbeddingAdapter
from app.generator.types import ArtifactScores, StyleConfig
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.services.embed_pipeline import index_user_experience
from app.services.generation import generate_for_job, score_baseline
from app.vectorstore.memory import InMemoryVectorStore

# ---------------------------------------------------------------------------
# Canned LLM responses
# ---------------------------------------------------------------------------

_RESUME_MD = (
    "# Jane Smith\n\n"
    "- Built Python ML pipelines processing 500k events/day.\n"
    "- Led team of 3 engineers achieving 40% latency improvement."
)
_RESUME_DOC_JSON = json.dumps({"markdown": _RESUME_MD})

_COVER_LETTER_MD = (
    "Dear Hiring Manager,\n\n"
    "I am excited to apply for the Senior ML Engineer role.\n\n"
    "In my previous role I reduced inference latency by 40%.\n\n"
    "Best regards,\nJane"
)
_COVER_LETTER_DOC_JSON = json.dumps({"markdown": _COVER_LETTER_MD})

_GROUNDEDNESS_JSON = json.dumps(
    {
        "claims": [
            {
                "text": "Built Python ML pipelines processing 500k events/day.",
                "experience_id": None,
                "grounded": False,
            },
            {
                "text": "Led team of 3 engineers achieving 40% latency improvement.",
                "experience_id": str(uuid.uuid4()),
                "grounded": True,
            },
        ],
        "grounded_ratio": 0.5,
        "ungrounded": ["Built Python ML pipelines processing 500k events/day."],
    }
)

# Canned groundedness result with no claims (for baseline with no experience items)
_GROUNDEDNESS_EMPTY_JSON = json.dumps(
    {
        "claims": [],
        "grounded_ratio": 0.0,
        "ungrounded": [],
    }
)

# Canned groundedness result for baseline with 2 quantified bullets
_GROUNDEDNESS_TWO_THIRDS_JSON = json.dumps(
    {
        "claims": [
            {
                "text": "Reduced latency by 40%.",
                "experience_id": str(uuid.uuid4()),
                "grounded": True,
            },
            {
                "text": "Improved throughput by 3x.",
                "experience_id": str(uuid.uuid4()),
                "grounded": True,
            },
            {
                "text": "Led a team.",
                "experience_id": None,
                "grounded": False,
            },
        ],
        "grounded_ratio": 0.667,
        "ungrounded": ["Led a team."],
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(required_skills: list[str] | None = None) -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        source="test",
        source_url="https://example.com/job/1",
        source_id=str(uuid.uuid4()),
        company="ML Corp",
        title="Senior Python ML Engineer",
        raw_content="Python, ML, PyTorch required.",
        extracted={
            "required_skills": required_skills or ["Python", "ML", "PyTorch"],
            "summary": "Build ML systems at scale.",
            "responsibilities": ["Design ML pipelines", "Lead engineers"],
            "culture_signals": ["fast-paced", "ownership"],
        },
    )


async def _seed(session, n: int = 2) -> tuple[User, list[ExperienceItem]]:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", name="Jane")
    session.add(user)
    items = [
        ExperienceItem(
            id=uuid.uuid4(),
            user_id=user.id,
            kind="work",
            title=f"Role {i}",
            content=f"Python ML work {i}, improved metrics by {i * 10}%.",
        )
        for i in range(n)
    ]
    for item in items:
        session.add(item)
    await session.flush()
    return user, items


# ---------------------------------------------------------------------------
# generate_for_job — resume
# ---------------------------------------------------------------------------


class TestGenerateForJobResume:
    async def test_persists_artifact_with_scores(self, session) -> None:
        # Arrange
        user, _ = await _seed(session)
        job = _make_job()
        session.add(job)
        await session.flush()

        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        await index_user_experience(session, embed, store, user.id)

        # Two LLM calls: generate_resume + check_groundedness
        adapter = MockAdapter(responses=[_RESUME_DOC_JSON, _GROUNDEDNESS_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        # Act
        artifact = await generate_for_job(
            session, llm, embed, store, user.id, job, "resume", StyleConfig()
        )
        await session.commit()

        # Assert
        assert isinstance(artifact, Artifact)
        assert artifact.user_id == user.id
        assert artifact.job_id == job.id
        assert artifact.kind == "resume"
        assert artifact.format == "markdown"
        assert artifact.content == _RESUME_MD
        assert artifact.is_baseline is False

    async def test_artifact_has_scores(self, session) -> None:
        user, _ = await _seed(session)
        job = _make_job()
        session.add(job)
        await session.flush()

        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        await index_user_experience(session, embed, store, user.id)

        adapter = MockAdapter(responses=[_RESUME_DOC_JSON, _GROUNDEDNESS_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        artifact = await generate_for_job(
            session, llm, embed, store, user.id, job, "resume", StyleConfig()
        )
        await session.commit()

        assert artifact.scores is not None
        scores = ArtifactScores(**artifact.scores)
        assert 0.0 <= scores.groundedness <= 1.0
        assert 0.0 <= scores.ats_keywords <= 1.0
        assert 0.0 <= scores.quantified_impact <= 1.0
        assert 0.0 <= scores.clarity <= 1.0

    async def test_artifact_has_prompt_version_id(self, session) -> None:
        user, _ = await _seed(session)
        job = _make_job()
        session.add(job)
        await session.flush()

        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        await index_user_experience(session, embed, store, user.id)

        adapter = MockAdapter(responses=[_RESUME_DOC_JSON, _GROUNDEDNESS_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        artifact = await generate_for_job(
            session, llm, embed, store, user.id, job, "resume", StyleConfig()
        )
        await session.commit()

        assert artifact.prompt_version_id is not None

    async def test_invalid_kind_raises(self, session) -> None:
        user, _ = await _seed(session)
        job = _make_job()
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        with pytest.raises(ValueError, match="kind must be"):
            await generate_for_job(
                session, llm, embed, store, user.id, job, "invalid_kind", StyleConfig()
            )


# ---------------------------------------------------------------------------
# generate_for_job — cover letter
# ---------------------------------------------------------------------------


class TestGenerateForJobCoverLetter:
    async def test_persists_cover_letter_artifact(self, session) -> None:
        user, _ = await _seed(session)
        job = _make_job()
        session.add(job)
        await session.flush()

        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        await index_user_experience(session, embed, store, user.id)

        adapter = MockAdapter(responses=[_COVER_LETTER_DOC_JSON, _GROUNDEDNESS_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        artifact = await generate_for_job(
            session, llm, embed, store, user.id, job, "cover_letter", StyleConfig()
        )
        await session.commit()

        assert artifact.kind == "cover_letter"
        assert artifact.content == _COVER_LETTER_MD
        assert artifact.scores is not None


# ---------------------------------------------------------------------------
# score_baseline
# ---------------------------------------------------------------------------


class TestScoreBaseline:
    async def test_returns_artifact_scores(self, session) -> None:
        # score_baseline now calls check_groundedness (1 LLM call).
        # User has no experience items so empty claims → grounded_ratio=0.0.
        adapter = MockAdapter(responses=[_GROUNDEDNESS_EMPTY_JSON])
        llm = LLMClient(session=session, adapter=adapter)
        user_id = uuid.uuid4()

        baseline_md = (
            "# My Resume\n\n"
            "- Delivered 3 major features on time.\n"
            "- Reduced build time by 25%.\n"
            "- Mentored junior developers."
        )

        scores = await score_baseline(session, llm, user_id, baseline_md)

        assert isinstance(scores, ArtifactScores)
        assert scores.fit == pytest.approx(0.0)
        assert scores.ats_keywords == pytest.approx(0.0)
        # grounded_ratio recomputed from empty claims → 0.0
        assert scores.groundedness == pytest.approx(0.0)

    async def test_quantified_impact_detected(self, session) -> None:
        # score_baseline now calls check_groundedness (1 LLM call).
        adapter = MockAdapter(responses=[_GROUNDEDNESS_TWO_THIRDS_JSON])
        llm = LLMClient(session=session, adapter=adapter)
        user_id = uuid.uuid4()

        baseline_md = "- Reduced latency by 40%.\n- Improved throughput by 3x.\n- Led a team."

        scores = await score_baseline(session, llm, user_id, baseline_md)

        # 2 of 3 bullets are quantified
        assert scores.quantified_impact == pytest.approx(2 / 3)

    async def test_clarity_within_range(self, session) -> None:
        adapter = MockAdapter(responses=[_GROUNDEDNESS_EMPTY_JSON])
        llm = LLMClient(session=session, adapter=adapter)
        user_id = uuid.uuid4()

        short_md = "# Resume\n\n- One bullet."
        scores = await score_baseline(session, llm, user_id, short_md)

        assert 0.0 <= scores.clarity <= 1.0

    async def test_groundedness_measured_via_llm(self, session) -> None:
        """score_baseline now measures groundedness with check_groundedness."""
        # Seed a user and experience items so groundedness can be meaningful.
        user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", name="Test")
        session.add(user)
        item = ExperienceItem(
            id=uuid.uuid4(),
            user_id=user.id,
            kind="work",
            title="Engineer",
            content="Reduced latency by 40% at Acme Corp.",
        )
        session.add(item)
        await session.flush()

        # MockAdapter returns a fully-grounded result
        grounded_json = json.dumps(
            {
                "claims": [
                    {
                        "text": "Reduced latency by 40%.",
                        "experience_id": str(item.id),
                        "grounded": True,
                    }
                ],
                "grounded_ratio": 1.0,
                "ungrounded": [],
            }
        )
        adapter = MockAdapter(responses=[grounded_json])
        llm = LLMClient(session=session, adapter=adapter)

        scores = await score_baseline(
            session, llm, user.id, "- Reduced latency by 40%."
        )

        assert scores.groundedness == pytest.approx(1.0)
