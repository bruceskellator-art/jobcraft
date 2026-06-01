"""Integration tests for app.eval.runner.run_suite.

The runner is session-safe: each case runs on its own session from the
factory. These tests build a session factory bound to the conftest in-memory
SQLite engine and pass an llm_factory that binds a shared MockAdapter to each
per-case session.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import make_session_factory
from app.db.models.eval_run import EvalRun
from app.embeddings.fake import FakeEmbeddingAdapter
from app.eval.runner import run_suite
from app.eval.types import (
    ContainsSkillAssertion,
    EvalCase,
    EvalSuite,
    GroundednessAssertion,
    LengthAssertion,
)
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.vectorstore.memory import InMemoryVectorStore

# ---------------------------------------------------------------------------
# Canned mock responses
# ---------------------------------------------------------------------------

_RESUME_MD = (
    "# Test Candidate\n\n"
    "- Built Python AI systems at scale.\n"
    "- Led team of engineers delivering measurable impact.\n"
    "- Applied machine learning to production workloads.\n"
)

_GROUNDEDNESS_JSON = json.dumps({
    "claims": [
        {"text": "Built Python AI systems at scale.", "experience_id": None, "grounded": True},
    ],
    "grounded_ratio": 1.0,
    "ungrounded": [],
})


def _make_mock_fn(resume_md: str = _RESUME_MD, groundedness_json: str = _GROUNDEDNESS_JSON):
    """Returns a callable that dispatches canned responses by prompt content.

    The groundedness check prompt contains the unique marker "anti-hallucination judge".
    The llm_judge prompt contains "expert evaluator". All other prompts are resume generation.
    """
    def _fn(prompt: str) -> str:
        p = prompt.lower()
        if "anti-hallucination" in p:
            return groundedness_json
        if "expert evaluator" in p:
            return json.dumps({"score": 0.85, "rationale": "Good quality"})
        return json.dumps({"markdown": resume_md})
    return _fn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_factory(fn=None):
    """Build an llm_factory that binds a shared MockAdapter to each session."""
    adapter = MockAdapter(fn=fn or _make_mock_fn())

    def _factory(session: AsyncSession) -> LLMClient:
        return LLMClient(session=session, adapter=adapter)

    return _factory


async def _seed_prompt_version(session_factory) -> uuid.UUID:
    """Ensure the resume prompt version exists (committed) and return its ID."""
    from app.generator.service import ensure_resume_prompt

    async with session_factory() as session:
        pv = await ensure_resume_prompt(session)
        await session.commit()
        return pv.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunSuite:
    async def test_run_suite_persists_eval_run(self, engine) -> None:
        """run_suite should persist an EvalRun via its own session."""
        session_factory = make_session_factory(engine)
        llm_factory = _make_llm_factory()
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        prompt_version_id = await _seed_prompt_version(session_factory)

        suite = EvalSuite(
            name="test_suite",
            description="Test",
            cases=[
                EvalCase(
                    id="case_001",
                    assertions=[
                        ContainsSkillAssertion(skill="Python"),
                        LengthAssertion(min_words=5),
                    ],
                )
            ],
        )

        eval_run = await run_suite(
            session_factory,
            suite,
            prompt_version_id=prompt_version_id,
            llm_factory=llm_factory,
            embed=embed,
            store=store,
        )

        assert isinstance(eval_run, EvalRun)
        assert eval_run.suite_name == "test_suite"
        assert eval_run.prompt_version_id == prompt_version_id
        assert eval_run.started_at is not None
        assert eval_run.completed_at is not None
        assert isinstance(eval_run.results, list)
        assert len(eval_run.results) == 1

    async def test_eval_run_readable_from_fresh_session(self, engine) -> None:
        """The persisted EvalRun should be queryable on a brand-new session."""
        session_factory = make_session_factory(engine)
        llm_factory = _make_llm_factory()
        prompt_version_id = await _seed_prompt_version(session_factory)

        suite = EvalSuite(
            name="persisted_suite",
            cases=[EvalCase(id="c1", assertions=[ContainsSkillAssertion(skill="Python")])],
        )

        eval_run = await run_suite(
            session_factory, suite,
            prompt_version_id=prompt_version_id,
            llm_factory=llm_factory,
            embed=FakeEmbeddingAdapter(dim=64),
            store=InMemoryVectorStore(),
        )

        from sqlalchemy import select

        async with session_factory() as verify_session:
            result = await verify_session.execute(
                select(EvalRun).where(EvalRun.id == eval_run.id)
            )
            fetched = result.scalar_one()
            assert fetched.suite_name == "persisted_suite"

    async def test_aggregate_contains_pass_rate(self, engine) -> None:
        """Aggregate scores must include pass_rate key."""
        session_factory = make_session_factory(engine)
        llm_factory = _make_llm_factory()
        prompt_version_id = await _seed_prompt_version(session_factory)

        suite = EvalSuite(
            name="agg_suite",
            cases=[
                EvalCase(id="c1", assertions=[ContainsSkillAssertion(skill="Python")])
            ],
        )

        eval_run = await run_suite(
            session_factory, suite,
            prompt_version_id=prompt_version_id,
            llm_factory=llm_factory,
            embed=FakeEmbeddingAdapter(dim=64),
            store=InMemoryVectorStore(),
        )

        assert "pass_rate" in eval_run.aggregate_scores

    async def test_failing_assertion_reflected_in_aggregate(self, engine) -> None:
        """A failing assertion should lower the pass_rate below 1.0."""
        session_factory = make_session_factory(engine)
        llm_factory = _make_llm_factory(
            _make_mock_fn(resume_md="# Candidate\n\n- Python work experience only.\n")
        )
        prompt_version_id = await _seed_prompt_version(session_factory)

        suite = EvalSuite(
            name="fail_suite",
            cases=[
                EvalCase(id="c1", assertions=[ContainsSkillAssertion(skill="Rust")])  # fails
            ],
        )

        eval_run = await run_suite(
            session_factory, suite,
            prompt_version_id=prompt_version_id,
            llm_factory=llm_factory,
            embed=FakeEmbeddingAdapter(dim=64),
            store=InMemoryVectorStore(),
        )

        assert eval_run.aggregate_scores["pass_rate"] < 1.0
        case_result = eval_run.results[0]
        assert case_result["passed"] is False

    async def test_failing_assertion_does_not_crash_run(self, engine) -> None:
        """Even if one assertion fails, the run completes and records all results."""
        session_factory = make_session_factory(engine)
        llm_factory = _make_llm_factory()
        prompt_version_id = await _seed_prompt_version(session_factory)

        suite = EvalSuite(
            name="mixed_suite",
            cases=[
                EvalCase(
                    id="c1",
                    assertions=[
                        ContainsSkillAssertion(skill="Python"),  # passes
                        ContainsSkillAssertion(skill="COBOL"),   # fails
                    ],
                )
            ],
        )

        eval_run = await run_suite(
            session_factory, suite,
            prompt_version_id=prompt_version_id,
            llm_factory=llm_factory,
            embed=FakeEmbeddingAdapter(dim=64),
            store=InMemoryVectorStore(),
        )

        assert len(eval_run.results) == 1
        assertion_results = eval_run.results[0]["assertions"]
        assert len(assertion_results) == 2
        kinds = {ar["kind"] for ar in assertion_results}
        assert kinds == {"contains_skill"}

    async def test_multiple_cases_all_recorded(self, engine) -> None:
        """All cases should be recorded when running multiple concurrently."""
        session_factory = make_session_factory(engine)
        llm_factory = _make_llm_factory()
        prompt_version_id = await _seed_prompt_version(session_factory)

        suite = EvalSuite(
            name="multi_suite",
            cases=[
                EvalCase(id="c1", assertions=[ContainsSkillAssertion(skill="Python")]),
                EvalCase(id="c2", assertions=[LengthAssertion(min_words=5)]),
                EvalCase(id="c3", assertions=[ContainsSkillAssertion(skill="Python")]),
            ],
        )

        eval_run = await run_suite(
            session_factory, suite,
            prompt_version_id=prompt_version_id,
            llm_factory=llm_factory,
            embed=FakeEmbeddingAdapter(dim=64),
            store=InMemoryVectorStore(),
        )

        assert len(eval_run.results) == 3
        case_ids = {r["case_id"] for r in eval_run.results}
        assert case_ids == {"c1", "c2", "c3"}

    async def test_groundedness_assertion_recorded_in_results(self, engine) -> None:
        """A groundedness assertion should produce a result with kind='groundedness'."""
        session_factory = make_session_factory(engine)
        llm_factory = _make_llm_factory()
        prompt_version_id = await _seed_prompt_version(session_factory)

        suite = EvalSuite(
            name="grnd_suite",
            cases=[
                EvalCase(id="c1", assertions=[GroundednessAssertion(threshold=0.5)])
            ],
        )

        eval_run = await run_suite(
            session_factory, suite,
            prompt_version_id=prompt_version_id,
            llm_factory=llm_factory,
            embed=FakeEmbeddingAdapter(dim=64),
            store=InMemoryVectorStore(),
        )

        assertion_results = eval_run.results[0]["assertions"]
        assert any(ar["kind"] == "groundedness" for ar in assertion_results)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


class TestCliMockMode:
    async def test_cli_eval_run_mock_exits_zero_or_one(self) -> None:
        """_cmd_eval_run should return 0 (pass) or 1 (fail), not 2 (error)."""
        from app.cli import _cmd_eval_run

        exit_code = await _cmd_eval_run("resume_quality_v1", None, mock=True)

        # 0 = all passed, 1 = some failed — both are acceptable; 2 would be an error
        assert exit_code in (0, 1)
