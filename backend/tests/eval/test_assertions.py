"""Unit tests for app.eval.assertions — deterministic and LLM-backed runners."""

from __future__ import annotations

import json

import pytest

from app.eval.assertions import run_contains_skill, run_excludes_phrase, run_length
from app.eval.types import (
    ContainsSkillAssertion,
    ExcludesPhraseAssertion,
    GroundednessAssertion,
    LengthAssertion,
    LlmJudgeAssertion,
)

# ---------------------------------------------------------------------------
# contains_skill
# ---------------------------------------------------------------------------


class TestContainsSkill:
    def test_passes_when_skill_present(self) -> None:
        assertion = ContainsSkillAssertion(skill="Python")
        result = run_contains_skill(assertion, "Experience with Python and Django.")
        assert result.passed is True
        assert result.kind == "contains_skill"
        assert result.score is None

    def test_fails_when_skill_absent(self) -> None:
        assertion = ContainsSkillAssertion(skill="Rust")
        result = run_contains_skill(assertion, "Experience with Python and Django.")
        assert result.passed is False

    def test_case_insensitive(self) -> None:
        assertion = ContainsSkillAssertion(skill="python")
        result = run_contains_skill(assertion, "Experience with PYTHON.")
        assert result.passed is True

    def test_word_boundary_match(self) -> None:
        # "SQL" must not match "NoSQL" as a whole word
        assertion = ContainsSkillAssertion(skill="SQL")
        result = run_contains_skill(assertion, "Worked with NoSQL databases.")
        assert result.passed is False

    def test_word_boundary_exact(self) -> None:
        assertion = ContainsSkillAssertion(skill="SQL")
        result = run_contains_skill(assertion, "Worked with SQL and PostgreSQL.")
        assert result.passed is True


# ---------------------------------------------------------------------------
# excludes_phrase
# ---------------------------------------------------------------------------


class TestExcludesPhrase:
    def test_passes_when_phrase_absent(self) -> None:
        assertion = ExcludesPhraseAssertion(phrase="I cannot")
        result = run_excludes_phrase(assertion, "Here is a tailored resume.")
        assert result.passed is True
        assert result.kind == "excludes_phrase"

    def test_fails_when_phrase_present(self) -> None:
        assertion = ExcludesPhraseAssertion(phrase="I cannot")
        result = run_excludes_phrase(assertion, "I cannot provide that information.")
        assert result.passed is False

    def test_case_insensitive_match(self) -> None:
        assertion = ExcludesPhraseAssertion(phrase="error")
        result = run_excludes_phrase(assertion, "An ERROR occurred.")
        assert result.passed is False

    def test_passes_when_substring_absent(self) -> None:
        assertion = ExcludesPhraseAssertion(phrase="hallucinated")
        result = run_excludes_phrase(assertion, "This resume is grounded in real experience.")
        assert result.passed is True


# ---------------------------------------------------------------------------
# length
# ---------------------------------------------------------------------------


class TestLength:
    def test_passes_within_bounds(self) -> None:
        text = " ".join(["word"] * 100)
        assertion = LengthAssertion(min_words=50, max_words=200)
        result = run_length(assertion, text)
        assert result.passed is True
        assert result.kind == "length"
        assert "word_count=100" in result.detail

    def test_fails_too_short(self) -> None:
        text = "Only ten words here in this short sentence yeah."
        assertion = LengthAssertion(min_words=50)
        result = run_length(assertion, text)
        assert result.passed is False

    def test_fails_too_long(self) -> None:
        text = " ".join(["word"] * 500)
        assertion = LengthAssertion(max_words=300)
        result = run_length(assertion, text)
        assert result.passed is False

    def test_no_min_only_max(self) -> None:
        text = " ".join(["word"] * 10)
        assertion = LengthAssertion(max_words=20)
        result = run_length(assertion, text)
        assert result.passed is True

    def test_no_max_only_min(self) -> None:
        text = " ".join(["word"] * 100)
        assertion = LengthAssertion(min_words=50)
        result = run_length(assertion, text)
        assert result.passed is True

    def test_exact_boundary_min(self) -> None:
        text = " ".join(["word"] * 50)
        assertion = LengthAssertion(min_words=50)
        result = run_length(assertion, text)
        assert result.passed is True

    def test_exact_boundary_max(self) -> None:
        text = " ".join(["word"] * 50)
        assertion = LengthAssertion(max_words=50)
        result = run_length(assertion, text)
        assert result.passed is True


# ---------------------------------------------------------------------------
# groundedness (LLM-backed, mocked)
# ---------------------------------------------------------------------------


class TestGroundednessAssertion:
    async def test_passes_when_above_threshold(self, session) -> None:
        from app.eval.assertions import run_groundedness
        from app.llm.adapters.mock import MockAdapter
        from app.llm.client import LLMClient

        grounded_json = json.dumps({
            "claims": [
                {"text": "Led team of 3.", "experience_id": None, "grounded": True},
            ],
            "grounded_ratio": 1.0,
            "ungrounded": [],
        })

        adapter = MockAdapter(responses=[grounded_json])
        llm = LLMClient(session=session, adapter=adapter)
        assertion = GroundednessAssertion(threshold=0.8)

        result = await run_groundedness(
            assertion, "Led team of 3.", session=session, llm=llm, experience_items=[]
        )

        assert result.passed is True
        assert result.kind == "groundedness"
        assert result.score == pytest.approx(1.0)

    async def test_fails_when_below_threshold(self, session) -> None:
        from app.eval.assertions import run_groundedness
        from app.llm.adapters.mock import MockAdapter
        from app.llm.client import LLMClient

        low_json = json.dumps({
            "claims": [
                {"text": "Invented claims.", "experience_id": None, "grounded": False},
            ],
            "grounded_ratio": 0.0,
            "ungrounded": ["Invented claims."],
        })

        adapter = MockAdapter(responses=[low_json])
        llm = LLMClient(session=session, adapter=adapter)
        assertion = GroundednessAssertion(threshold=0.9)

        result = await run_groundedness(
            assertion, "Invented claims.", session=session, llm=llm, experience_items=[]
        )

        assert result.passed is False
        assert result.score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# llm_judge (LLM-backed, mocked)
# ---------------------------------------------------------------------------


class TestLlmJudgeAssertion:
    async def test_passes_when_score_above_threshold(self, session) -> None:
        from app.eval.assertions import run_llm_judge
        from app.llm.adapters.mock import MockAdapter
        from app.llm.client import LLMClient

        judge_json = json.dumps({"score": 0.85, "rationale": "Good resume"})
        adapter = MockAdapter(responses=[judge_json])
        llm = LLMClient(session=session, adapter=adapter)
        assertion = LlmJudgeAssertion(rubric="Rate the resume 0-1.", threshold=0.7)

        result = await run_llm_judge(assertion, "A well written resume.", session=session, llm=llm)

        assert result.passed is True
        assert result.kind == "llm_judge"
        assert result.score == pytest.approx(0.85)

    async def test_fails_when_score_below_threshold(self, session) -> None:
        from app.eval.assertions import run_llm_judge
        from app.llm.adapters.mock import MockAdapter
        from app.llm.client import LLMClient

        judge_json = json.dumps({"score": 0.4, "rationale": "Poor quality"})
        adapter = MockAdapter(responses=[judge_json])
        llm = LLMClient(session=session, adapter=adapter)
        assertion = LlmJudgeAssertion(rubric="Rate the resume 0-1.", threshold=0.7)

        result = await run_llm_judge(assertion, "A bad resume.", session=session, llm=llm)

        assert result.passed is False
        assert result.score == pytest.approx(0.4)
