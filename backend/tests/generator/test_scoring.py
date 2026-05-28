"""Unit tests for deterministic scoring helpers in app.generator.scoring.

All tests are pure — no database, no LLM, no network.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.models.job_posting import JobPosting
from app.generator.scoring import (
    compose_artifact_scores,
    score_ats_keywords,
    score_clarity,
    score_quantified_impact,
)
from app.generator.types import ArtifactScores, Claim, GroundednessResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(required_skills: list[str] | None = None) -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        source="test",
        source_url="https://example.com/job/1",
        source_id="j1",
        company="Acme",
        title="Software Engineer",
        raw_content="Python, SQL, Docker required.",
        extracted={"required_skills": required_skills or [], "summary": ""},
    )


def _make_groundedness(grounded_ratio: float = 1.0) -> GroundednessResult:
    return GroundednessResult(
        claims=[
            Claim(text="Led a team", experience_id=uuid.uuid4(), grounded=True)
        ],
        grounded_ratio=grounded_ratio,
        ungrounded=[],
    )


# ---------------------------------------------------------------------------
# score_ats_keywords
# ---------------------------------------------------------------------------


class TestScoreAtsKeywords:
    def test_full_coverage(self) -> None:
        job = _make_job(["Python", "SQL", "Docker"])
        md = "# Resume\n- Built Python services with SQL and Docker."
        assert score_ats_keywords(md, job) == pytest.approx(1.0)

    def test_partial_coverage(self) -> None:
        job = _make_job(["Python", "SQL", "Kubernetes"])
        md = "- Python developer with SQL experience."
        score = score_ats_keywords(md, job)
        assert score == pytest.approx(2 / 3)

    def test_no_coverage(self) -> None:
        job = _make_job(["Rust", "Go"])
        md = "- Java and C++ developer."
        assert score_ats_keywords(md, job) == pytest.approx(0.0)

    def test_case_insensitive(self) -> None:
        job = _make_job(["python", "DOCKER"])
        md = "- Used Python and docker."
        assert score_ats_keywords(md, job) == pytest.approx(1.0)

    def test_no_extracted_returns_zero(self) -> None:
        job = JobPosting(
            id=uuid.uuid4(),
            source="test",
            source_url="https://example.com/job/2",
            source_id="j2",
            company="Co",
            title="Dev",
            raw_content="Python required.",
            extracted=None,
        )
        assert score_ats_keywords("Python", job) == pytest.approx(0.0)

    def test_empty_required_skills_returns_zero(self) -> None:
        job = _make_job([])
        assert score_ats_keywords("Python", job) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# score_quantified_impact
# ---------------------------------------------------------------------------


class TestScoreQuantifiedImpact:
    def test_all_quantified(self) -> None:
        md = "- Improved latency by 40%\n- Managed 5 engineers\n- Reduced costs by $200k"
        assert score_quantified_impact(md) == pytest.approx(1.0)

    def test_none_quantified(self) -> None:
        md = "- Led a team\n- Improved performance\n- Built features"
        assert score_quantified_impact(md) == pytest.approx(0.0)

    def test_partial_quantified(self) -> None:
        md = "- Improved latency by 40%\n- Led a team"
        assert score_quantified_impact(md) == pytest.approx(0.5)

    def test_no_bullets_returns_zero(self) -> None:
        md = "# Resume\n\nSome paragraph without bullets."
        assert score_quantified_impact(md) == pytest.approx(0.0)

    def test_mixed_bullet_styles(self) -> None:
        md = "- 50% faster\n* no numbers here"
        assert score_quantified_impact(md) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# score_clarity
# ---------------------------------------------------------------------------


class TestScoreClarity:
    def test_under_target_is_one(self) -> None:
        # 10 words — well under 600 target
        md = " ".join(["word"] * 10)
        assert score_clarity(md, "one_page") == pytest.approx(1.0)

    def test_at_target_is_one(self) -> None:
        md = " ".join(["word"] * 600)
        assert score_clarity(md, "one_page") == pytest.approx(1.0)

    def test_at_ceiling_is_zero(self) -> None:
        # ceiling = 600 * 1.5 = 900 words
        md = " ".join(["word"] * 900)
        assert score_clarity(md, "one_page") == pytest.approx(0.0)

    def test_above_ceiling_is_zero(self) -> None:
        md = " ".join(["word"] * 1200)
        assert score_clarity(md, "one_page") == pytest.approx(0.0)

    def test_midpoint_is_half(self) -> None:
        # midpoint = 600 + (900 - 600) / 2 = 750
        md = " ".join(["word"] * 750)
        assert score_clarity(md, "one_page") == pytest.approx(0.5)

    def test_two_page_target(self) -> None:
        md = " ".join(["word"] * 1200)
        assert score_clarity(md, "two_page") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# compose_artifact_scores
# ---------------------------------------------------------------------------


class TestComposeArtifactScores:
    def test_fit_from_match(self) -> None:
        from app.db.models.match import Match

        match = Match(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            overall_score=0.82,
            dimension_scores={},
            gaps=[],
            rationale="Good.",
            prompt_version_id=uuid.uuid4(),
        )
        job = _make_job(["Python"])
        groundedness = _make_groundedness(0.9)
        md = "- Python engineer with 5 years experience."
        scores = compose_artifact_scores(md, job, groundedness, match)
        assert isinstance(scores, ArtifactScores)
        assert scores.fit == pytest.approx(0.82)
        assert scores.groundedness == pytest.approx(0.9)

    def test_fit_zero_when_no_match(self) -> None:
        job = _make_job(["Python"])
        groundedness = _make_groundedness(0.75)
        md = "- Python developer."
        scores = compose_artifact_scores(md, job, groundedness, None)
        assert scores.fit == pytest.approx(0.0)

    def test_all_scores_in_range(self) -> None:
        job = _make_job(["Python", "SQL"])
        groundedness = _make_groundedness(0.8)
        md = "- Built Python pipelines processing 1M rows per day.\n- SQL query optimisation."
        scores = compose_artifact_scores(md, job, groundedness, None)
        for field, value in scores.model_dump().items():
            assert 0.0 <= value <= 1.0, f"{field}={value} out of [0, 1]"
