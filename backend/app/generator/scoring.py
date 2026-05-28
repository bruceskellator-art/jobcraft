"""Deterministic artifact scoring helpers.

All functions here are pure/side-effect-free so they can be unit-tested
without a database session or LLM. score_artifact composes them alongside
the LLM-derived groundedness result.
"""

from __future__ import annotations

import re

from app.db.models.job_posting import JobPosting
from app.db.models.match import Match
from app.generator.types import ArtifactScores, GroundednessResult

# Matches lines that look like resume bullets (starting with -, *, or a digit+dot)
_BULLET_RE = re.compile(r"^\s*[-*]|\s*\d+\.\s")
# Matches a digit or percentage somewhere in the line
_QUANTIFIED_RE = re.compile(r"\d|%")


def score_ats_keywords(markdown: str, job: JobPosting) -> float:
    """Coverage of required_skills from the JD that appear in the markdown.

    Case-insensitive substring match. Returns 0.0 if the job has no
    required_skills extracted.
    """
    if job.extracted is None:
        return 0.0
    required: list[str] = job.extracted.get("required_skills", []) or []
    if not required:
        return 0.0
    lower_md = markdown.lower()
    matched = sum(1 for skill in required if skill.lower() in lower_md)
    return matched / len(required)


def score_quantified_impact(markdown: str) -> float:
    """Share of bullet lines that contain a digit or percentage symbol.

    Returns 0.0 if there are no bullet lines.
    """
    bullet_lines = [line for line in markdown.splitlines() if _BULLET_RE.match(line)]
    if not bullet_lines:
        return 0.0
    quantified = sum(1 for line in bullet_lines if _QUANTIFIED_RE.search(line))
    return quantified / len(bullet_lines)


def score_clarity(markdown: str, length: str = "one_page") -> float:
    """Length-discipline heuristic.

    One-page target: ~600 words optimal. Two-page: ~1200 words.
    Score decays linearly if the document exceeds 1.5× the target.
    Score is 1.0 at or under target, 0.0 at or above 1.5× target.
    """
    target_words = 600 if length == "one_page" else 1200
    word_count = len(markdown.split())
    if word_count <= target_words:
        return 1.0
    ceiling = target_words * 1.5
    if word_count >= ceiling:
        return 0.0
    # Linear decay from 1.0 at target to 0.0 at ceiling
    excess = word_count - target_words
    range_width = ceiling - target_words
    return max(0.0, 1.0 - (excess / range_width))


def compose_artifact_scores(
    markdown: str,
    job: JobPosting,
    groundedness: GroundednessResult,
    match: Match | None,
    length: str = "one_page",
) -> ArtifactScores:
    """Compose all five scores into ArtifactScores.

    fit       — from match.overall_score if provided, else 0.0
    groundedness — from groundedness.grounded_ratio (LLM judge)
    ats_keywords — deterministic keyword coverage
    quantified_impact — deterministic bullet-line heuristic
    clarity — deterministic length-discipline heuristic
    """
    fit = match.overall_score if match is not None else 0.0
    return ArtifactScores(
        fit=fit,
        groundedness=groundedness.grounded_ratio,
        ats_keywords=score_ats_keywords(markdown, job),
        quantified_impact=score_quantified_impact(markdown),
        clarity=score_clarity(markdown, length),
    )
