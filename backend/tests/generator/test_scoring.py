"""Unit tests for deterministic scoring helpers in app.generator.scoring.

All tests are pure — no database, no LLM, no network.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.models.job_posting import JobPosting
from app.generator.scoring import (
    _BULLET_RE,
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
    """Build a GroundednessResult whose recomputed ratio matches grounded_ratio.

    The model validator derives grounded_ratio from claims, so we construct
    claims whose grounded/ungrounded split produces the desired ratio.
    Supports 0.0, 0.5, 0.75, 0.8, 0.9, and 1.0 via specific claim sets.
    """
    if grounded_ratio == 1.0:
        claims = [Claim(text="Led a team", experience_id=uuid.uuid4(), grounded=True)]
    elif grounded_ratio == 0.9:
        # 9 grounded + 1 ungrounded → 0.9
        claims = [
            Claim(text=f"Claim {i}", experience_id=uuid.uuid4(), grounded=True)
            for i in range(9)
        ] + [Claim(text="Ungrounded claim", experience_id=None, grounded=False)]
    elif grounded_ratio == 0.8:
        # 4 grounded + 1 ungrounded → 0.8
        claims = [
            Claim(text=f"Claim {i}", experience_id=uuid.uuid4(), grounded=True)
            for i in range(4)
        ] + [Claim(text="Ungrounded claim", experience_id=None, grounded=False)]
    elif grounded_ratio == 0.75:
        # 3 grounded + 1 ungrounded → 0.75
        claims = [
            Claim(text=f"Claim {i}", experience_id=uuid.uuid4(), grounded=True)
            for i in range(3)
        ] + [Claim(text="Ungrounded claim", experience_id=None, grounded=False)]
    elif grounded_ratio == 0.5:
        claims = [
            Claim(text="Grounded", experience_id=uuid.uuid4(), grounded=True),
            Claim(text="Ungrounded", experience_id=None, grounded=False),
        ]
    else:
        claims = []
    return GroundednessResult(
        claims=claims,
        grounded_ratio=grounded_ratio,  # overwritten by validator; just a placeholder
        ungrounded=[],  # overwritten by validator
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
        # "5" is a single digit and does not meet the tighter quantity-signal
        # threshold; use "50" (a multi-digit count) for a genuine quantity.
        md = "- Improved latency by 40%\n- Managed 50 engineers\n- Reduced costs by $200k"
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


# ---------------------------------------------------------------------------
# ATS keyword word-boundary regression (Fix #3)
# ---------------------------------------------------------------------------


class TestScoreAtsKeywordsWordBoundary:
    def test_go_skill_no_false_positive(self) -> None:
        """Skill 'Go' must NOT match mid-word occurrences like 'workflows'."""
        job = _make_job(["Go"])
        md = "- Manages category-level workflows."
        assert score_ats_keywords(md, job) == pytest.approx(0.0)

    def test_go_skill_matches_standalone(self) -> None:
        """Skill 'Go' SHOULD match when it appears as a whole word."""
        job = _make_job(["Go"])
        md = "- Developed services in Go and Python."
        assert score_ats_keywords(md, job) == pytest.approx(1.0)

    def test_skill_shorter_than_2_chars_skipped(self) -> None:
        """Single-character skills are skipped entirely."""
        job = _make_job(["C"])
        md = "- Expert in C programming and Python."
        # "C" is < 2 chars so it is excluded; no scorable skills → 0.0
        assert score_ats_keywords(md, job) == pytest.approx(0.0)

    def test_mixed_short_and_valid_skills(self) -> None:
        """Only skills >= 2 chars contribute to the denominator."""
        job = _make_job(["C", "Python"])
        md = "- Python developer."
        # "C" skipped; denominator = 1 (just "Python"); "Python" matched → 1.0
        assert score_ats_keywords(md, job) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Quantified impact tighter regex (Fix #4)
# ---------------------------------------------------------------------------


class TestScoreQuantifiedImpactTighter:
    def test_year_range_not_counted(self) -> None:
        """A bullet with only a year range ('2018 to 2021') is NOT quantified."""
        md = "- Worked at the company from 2018 to 2021."
        assert score_quantified_impact(md) == pytest.approx(0.0)

    def test_phase_number_not_counted(self) -> None:
        """'Phase 1' contains a single digit and should NOT be counted."""
        md = "- Delivered Phase 1 of the migration."
        assert score_quantified_impact(md) == pytest.approx(0.0)

    def test_percentage_counted(self) -> None:
        """'40%' is a valid quantity signal."""
        md = "- Reduced latency by 40%."
        assert score_quantified_impact(md) == pytest.approx(1.0)

    def test_currency_counted(self) -> None:
        """'$200k' is a valid quantity signal."""
        md = "- Saved the company $200k annually."
        assert score_quantified_impact(md) == pytest.approx(1.0)

    def test_multiplier_counted(self) -> None:
        """'3x' is a valid quantity signal."""
        md = "- Improved throughput by 3x."
        assert score_quantified_impact(md) == pytest.approx(1.0)

    def test_multi_digit_number_counted(self) -> None:
        """A 2-3 digit number (e.g. 50) counts as a quantity signal."""
        md = "- Managed team of 50 engineers."
        assert score_quantified_impact(md) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Bullet regex anchor (Fix #5)
# ---------------------------------------------------------------------------


class TestBulletRegexAnchor:
    def test_mid_line_version_not_a_bullet(self) -> None:
        """'version 2.0' mid-line must NOT be matched as a bullet."""
        line = "Released version 2.0 of the platform."
        assert _BULLET_RE.match(line) is None

    def test_hyphen_bullet_matches(self) -> None:
        assert _BULLET_RE.match("- Some achievement") is not None

    def test_star_bullet_matches(self) -> None:
        assert _BULLET_RE.match("* Another point") is not None

    def test_numbered_bullet_matches(self) -> None:
        assert _BULLET_RE.match("1. First item") is not None

    def test_indented_bullet_matches(self) -> None:
        assert _BULLET_RE.match("  - Indented bullet") is not None


# ---------------------------------------------------------------------------
# GroundednessResult validator (Fix #1)
# ---------------------------------------------------------------------------


class TestGroundednessResultValidator:
    def test_recomputes_ratio_from_claims(self) -> None:
        """grounded_ratio is recomputed from claims, ignoring LLM value."""
        result = GroundednessResult(
            claims=[
                Claim(text="Claim A", experience_id=uuid.uuid4(), grounded=True),
                Claim(text="Claim B", experience_id=None, grounded=False),
            ],
            grounded_ratio=0.99,  # LLM hallucinated value — must be overwritten
            ungrounded=[],
        )
        assert result.grounded_ratio == pytest.approx(0.5)

    def test_rebuilds_ungrounded_list(self) -> None:
        """ungrounded is rebuilt from claims where grounded=False."""
        result = GroundednessResult(
            claims=[
                Claim(text="True claim", experience_id=uuid.uuid4(), grounded=True),
                Claim(text="False claim", experience_id=None, grounded=False),
            ],
            grounded_ratio=1.0,
            ungrounded=["wrong"],  # LLM gave wrong list — must be overwritten
        )
        assert result.ungrounded == ["False claim"]

    def test_empty_claims_ratio_is_zero(self) -> None:
        """Empty claims list → grounded_ratio = 0.0, not 1.0."""
        result = GroundednessResult(
            claims=[],
            grounded_ratio=1.0,
            ungrounded=[],
        )
        assert result.grounded_ratio == pytest.approx(0.0)
        assert result.ungrounded == []

    def test_all_grounded_ratio_is_one(self) -> None:
        result = GroundednessResult(
            claims=[
                Claim(text="Claim A", experience_id=uuid.uuid4(), grounded=True),
                Claim(text="Claim B", experience_id=uuid.uuid4(), grounded=True),
            ],
            grounded_ratio=0.0,
            ungrounded=["wrong"],
        )
        assert result.grounded_ratio == pytest.approx(1.0)
        assert result.ungrounded == []
