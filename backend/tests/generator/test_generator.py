"""Unit tests for app.generator.service and app.generator.pdf."""

from __future__ import annotations

import json
import uuid

import pytest

from app.db.models.experience_item import ExperienceItem
from app.db.models.job_posting import JobPosting
from app.db.models.user import User
from app.embeddings.fake import FakeEmbeddingAdapter
from app.generator.pdf import NullPdfRenderer, PdfRenderError, TypstRenderer
from app.generator.service import (
    _retrieve_relevant_experience,
    check_groundedness,
    generate_resume,
    score_artifact,
)
from app.generator.types import ArtifactScores, Claim, GroundednessResult, StyleConfig
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.services.embed_pipeline import index_user_experience
from app.vectorstore.memory import InMemoryVectorStore

# ---------------------------------------------------------------------------
# Shared canned responses
# ---------------------------------------------------------------------------

_RESUME_MD = (
    "# Jane Smith\n\n"
    "- Built Python ML pipelines processing 500k events/day.\n"
    "- Led team of 3 engineers."
)

_RESUME_DOC_JSON = json.dumps({"markdown": _RESUME_MD})

_GROUNDEDNESS_JSON = json.dumps(
    {
        "claims": [
            {
                "text": "Built Python ML pipelines processing 500k events/day.",
                "experience_id": None,
                "grounded": False,
            },
            {
                "text": "Led team of 3 engineers.",
                "experience_id": str(uuid.uuid4()),
                "grounded": True,
            },
        ],
        "grounded_ratio": 0.5,
        "ungrounded": ["Built Python ML pipelines processing 500k events/day."],
    }
)


# ---------------------------------------------------------------------------
# Fixtures
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
        extracted={"required_skills": required_skills or ["Python", "ML"], "summary": ""},
    )


async def _seed_user(session, n: int = 3) -> tuple[User, list[ExperienceItem]]:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", name="Jane")
    session.add(user)
    items = [
        ExperienceItem(
            id=uuid.uuid4(),
            user_id=user.id,
            kind="work",
            title=f"Role {i}",
            content=f"Python ML work item {i} with quantified result {i * 10}%.",
        )
        for i in range(n)
    ]
    for item in items:
        session.add(item)
    await session.flush()
    return user, items


# ---------------------------------------------------------------------------
# _retrieve_relevant_experience
# ---------------------------------------------------------------------------


class TestRetrieveRelevantExperience:
    async def test_returns_ranked_items(self, session) -> None:
        user, items = await _seed_user(session, n=3)
        job = _make_job()
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        await index_user_experience(session, embed, store, user.id)

        retrieved = await _retrieve_relevant_experience(
            session, embed, store, user.id, job, top_n=3
        )

        assert len(retrieved) == 3
        assert all(isinstance(i, ExperienceItem) for i in retrieved)

    async def test_falls_back_when_store_empty(self, session) -> None:
        user, items = await _seed_user(session, n=2)
        job = _make_job()
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        # Do NOT call index_user_experience — store is empty

        retrieved = await _retrieve_relevant_experience(
            session, embed, store, user.id, job, top_n=5
        )

        # Falls back to all items
        assert len(retrieved) == 2

    async def test_top_n_limits_results(self, session) -> None:
        user, items = await _seed_user(session, n=5)
        job = _make_job()
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        await index_user_experience(session, embed, store, user.id)

        retrieved = await _retrieve_relevant_experience(
            session, embed, store, user.id, job, top_n=2
        )

        assert len(retrieved) <= 2

    async def test_stale_vector_ids_fallback_to_full_scan(self, session) -> None:
        """If the vector store returns IDs that no longer exist in the DB,
        fall back to a full scan rather than returning an empty list."""
        user, items = await _seed_user(session, n=2)
        job = _make_job()
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()

        # Index the items so the store has their IDs, then delete them from
        # the DB to simulate stale vectors pointing at deleted rows.
        await index_user_experience(session, embed, store, user.id)
        for item in items:
            await session.delete(item)
        await session.flush()

        # Re-seed fresh items that are NOT in the vector store.
        fresh_items = [
            ExperienceItem(
                id=uuid.uuid4(),
                user_id=user.id,
                kind="work",
                title="Fresh role",
                content="Fresh content not indexed in the vector store.",
            )
        ]
        for fi in fresh_items:
            session.add(fi)
        await session.flush()

        retrieved = await _retrieve_relevant_experience(
            session, embed, store, user.id, job, top_n=10
        )

        # The stale IDs map to nothing in DB, so fallback returns fresh items.
        assert len(retrieved) == len(fresh_items)
        assert retrieved[0].id == fresh_items[0].id

    async def test_most_relevant_items_ranked_first(self, session) -> None:
        """Items sharing tokens with the JD should rank higher."""
        user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", name="Test")
        session.add(user)
        item_relevant = ExperienceItem(
            id=uuid.uuid4(),
            user_id=user.id,
            kind="work",
            content="Python machine learning engineer with PyTorch experience.",
        )
        item_irrelevant = ExperienceItem(
            id=uuid.uuid4(),
            user_id=user.id,
            kind="work",
            content="Plumbing and construction project management.",
        )
        session.add(item_relevant)
        session.add(item_irrelevant)
        await session.flush()

        embed = FakeEmbeddingAdapter(dim=128)
        store = InMemoryVectorStore()
        await index_user_experience(session, embed, store, user.id)

        job = JobPosting(
            id=uuid.uuid4(),
            source="test",
            source_url="https://example.com/job/3",
            source_id=str(uuid.uuid4()),
            company="AI Co",
            title="Python Machine Learning Engineer",
            raw_content="Python machine learning PyTorch.",
            extracted=None,
        )

        retrieved = await _retrieve_relevant_experience(
            session, embed, store, user.id, job, top_n=2
        )

        assert retrieved[0].id == item_relevant.id


# ---------------------------------------------------------------------------
# generate_resume
# ---------------------------------------------------------------------------


class TestGenerateResume:
    async def test_returns_markdown_string(self, session) -> None:
        user, _ = await _seed_user(session)
        job = _make_job()
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        await index_user_experience(session, embed, store, user.id)

        adapter = MockAdapter(responses=[_RESUME_DOC_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        md, _ = await generate_resume(session, llm, embed, store, user.id, job, StyleConfig())

        assert isinstance(md, str)
        assert len(md) > 0

    async def test_uses_mock_adapter_response(self, session) -> None:
        user, _ = await _seed_user(session)
        job = _make_job()
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        await index_user_experience(session, embed, store, user.id)

        adapter = MockAdapter(responses=[_RESUME_DOC_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        md, _ = await generate_resume(session, llm, embed, store, user.id, job, StyleConfig())

        assert md == _RESUME_MD


# ---------------------------------------------------------------------------
# check_groundedness
# ---------------------------------------------------------------------------


class TestCheckGroundedness:
    async def test_parses_claims(self, session) -> None:
        user, items = await _seed_user(session)
        adapter = MockAdapter(responses=[_GROUNDEDNESS_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        result = await check_groundedness(session, llm, _RESUME_MD, items)

        assert isinstance(result, GroundednessResult)
        assert len(result.claims) == 2
        assert result.grounded_ratio == pytest.approx(0.5)

    async def test_ungrounded_list_populated(self, session) -> None:
        user, items = await _seed_user(session)
        adapter = MockAdapter(responses=[_GROUNDEDNESS_JSON])
        llm = LLMClient(session=session, adapter=adapter)

        result = await check_groundedness(session, llm, _RESUME_MD, items)

        assert len(result.ungrounded) == 1
        assert "500k" in result.ungrounded[0]

    async def test_fully_grounded_document(self, session) -> None:
        user, items = await _seed_user(session)
        fully_grounded = json.dumps(
            {
                "claims": [
                    {
                        "text": "Led team of 3.",
                        "experience_id": str(items[0].id),
                        "grounded": True,
                    }
                ],
                "grounded_ratio": 1.0,
                "ungrounded": [],
            }
        )
        adapter = MockAdapter(responses=[fully_grounded])
        llm = LLMClient(session=session, adapter=adapter)

        result = await check_groundedness(session, llm, "- Led team of 3.", items)

        assert result.grounded_ratio == pytest.approx(1.0)
        assert result.ungrounded == []


# ---------------------------------------------------------------------------
# score_artifact
# ---------------------------------------------------------------------------


class TestScoreArtifact:
    async def test_composes_artifact_scores(self, session) -> None:
        user, items = await _seed_user(session)
        job = _make_job(["Python", "ML"])
        groundedness = GroundednessResult(
            claims=[Claim(text="Python ML work.", experience_id=items[0].id, grounded=True)],
            grounded_ratio=1.0,
            ungrounded=[],
        )
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        md = "- Python ML pipelines processing 500k events/day.\n- Led 3 engineers."
        scores = await score_artifact(session, llm, md, job, groundedness, match=None)

        assert isinstance(scores, ArtifactScores)
        assert scores.fit == pytest.approx(0.0)
        assert scores.groundedness == pytest.approx(1.0)
        assert scores.ats_keywords > 0.0
        assert scores.quantified_impact > 0.0
        assert 0.0 <= scores.clarity <= 1.0

    async def test_fit_from_match(self, session) -> None:
        from app.db.models.match import Match

        user, items = await _seed_user(session)
        job = _make_job()
        match = Match(
            id=uuid.uuid4(),
            user_id=user.id,
            job_id=job.id,
            overall_score=0.77,
            dimension_scores={},
            gaps=[],
            rationale="Good fit.",
            prompt_version_id=uuid.uuid4(),
        )
        groundedness = GroundednessResult(claims=[], grounded_ratio=0.8, ungrounded=[])
        adapter = MockAdapter(responses=[])
        llm = LLMClient(session=session, adapter=adapter)

        scores = await score_artifact(session, llm, "- Led team.", job, groundedness, match)

        assert scores.fit == pytest.approx(0.77)


# ---------------------------------------------------------------------------
# NullPdfRenderer
# ---------------------------------------------------------------------------


class TestNullPdfRenderer:
    def test_returns_empty_bytes(self) -> None:
        renderer = NullPdfRenderer()
        result = renderer.render("# Resume\n\n- Some bullet.")
        assert result == b""

    def test_accepts_any_markdown(self) -> None:
        renderer = NullPdfRenderer()
        assert renderer.render("") == b""
        assert renderer.render("# Hello\n\n**bold**\n\n- bullet") == b""


class TestTypstRenderer:
    def test_raises_when_binary_missing(self) -> None:
        renderer = TypstRenderer(typst_bin="typst_binary_that_does_not_exist")
        with pytest.raises(PdfRenderError, match="not found"):
            renderer.render("# Hello")
