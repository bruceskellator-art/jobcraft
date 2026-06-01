"""Assertion runners: one function per assertion kind, each returning AssertionResult."""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from app.eval.types import (
    AssertionResult,
    ContainsSkillAssertion,
    ExcludesPhraseAssertion,
    GroundednessAssertion,
    LengthAssertion,
    LlmJudgeAssertion,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deterministic assertions (pure functions over generated text)
# ---------------------------------------------------------------------------


def run_contains_skill(assertion: ContainsSkillAssertion, text: str) -> AssertionResult:
    """Pass if skill appears as a whole word (case-insensitive) in text."""
    pattern = re.compile(r"\b" + re.escape(assertion.skill) + r"\b", re.IGNORECASE)
    passed = bool(pattern.search(text))
    detail = f"skill '{assertion.skill}' {'found' if passed else 'not found'} in output"
    return AssertionResult(kind="contains_skill", passed=passed, score=None, detail=detail)


def run_excludes_phrase(assertion: ExcludesPhraseAssertion, text: str) -> AssertionResult:
    """Pass if phrase does NOT appear anywhere in text (case-insensitive)."""
    passed = assertion.phrase.lower() not in text.lower()
    detail = f"phrase '{assertion.phrase}' {'absent' if passed else 'present'} in output"
    return AssertionResult(kind="excludes_phrase", passed=passed, score=None, detail=detail)


def run_length(assertion: LengthAssertion, text: str) -> AssertionResult:
    """Pass if word count is within the specified bounds."""
    word_count = len(text.split())
    too_short = assertion.min_words is not None and word_count < assertion.min_words
    too_long = assertion.max_words is not None and word_count > assertion.max_words
    passed = not too_short and not too_long

    parts: list[str] = [f"word_count={word_count}"]
    if assertion.min_words is not None:
        parts.append(f"min={assertion.min_words}")
    if assertion.max_words is not None:
        parts.append(f"max={assertion.max_words}")
    detail = ", ".join(parts)
    return AssertionResult(kind="length", passed=passed, score=None, detail=detail)


# ---------------------------------------------------------------------------
# LLM assertions
# ---------------------------------------------------------------------------


async def run_groundedness(
    assertion: GroundednessAssertion,
    text: str,
    *,
    session: object,
    llm: object,
    experience_items: list,
) -> AssertionResult:
    """Pass if grounded_ratio >= threshold.

    Reuses check_groundedness from app.generator.service; experience_items
    should be the ExperienceItem ORM instances used to generate the text.
    """
    from app.generator.service import check_groundedness  # type: ignore[attr-defined]

    try:
        result = await check_groundedness(session, llm, text, experience_items)  # type: ignore[arg-type]
        ratio = result.grounded_ratio
        passed = ratio >= assertion.threshold
        detail = (
            f"grounded_ratio={ratio:.3f}, threshold={assertion.threshold}, "
            f"ungrounded_count={len(result.ungrounded)}"
        )
        return AssertionResult(kind="groundedness", passed=passed, score=ratio, detail=detail)
    except Exception as exc:
        logger.error("run_groundedness failed: %s", exc)
        return AssertionResult(
            kind="groundedness",
            passed=False,
            score=0.0,
            detail=f"error: {exc}",
        )


class _JudgeScore(BaseModel):
    score: float
    rationale: str = ""


_LLM_JUDGE_PROMPT_NAME = "llm_judge_v1"
_LLM_JUDGE_TEMPLATE = """\
You are an expert evaluator. Score the following document against the rubric.

Return ONLY a JSON object — no prose, no fences — with this schema:
{"score": <float 0.0 to 1.0>, "rationale": "<brief reason>"}

<rubric>
{{ rubric }}
</rubric>

<document>
{{ document }}
</document>
"""


async def run_llm_judge(
    assertion: LlmJudgeAssertion,
    text: str,
    *,
    session: object,
    llm: object,
) -> AssertionResult:
    """Score the document against a rubric via LLM; pass if score >= threshold."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.prompt_version import PromptVersion

    typed_session: AsyncSession = session  # type: ignore[assignment]

    # Ensure the llm_judge prompt version exists
    result = await typed_session.execute(
        select(PromptVersion).where(
            PromptVersion.name == _LLM_JUDGE_PROMPT_NAME,
            PromptVersion.is_active == True,  # noqa: E712
        )
    )
    pv = result.scalar_one_or_none()
    if pv is None:
        new_pv = PromptVersion(
            name=_LLM_JUDGE_PROMPT_NAME,
            version=1,
            template=_LLM_JUDGE_TEMPLATE,
            model="claude-sonnet-4-6",
            temperature=0.0,
            is_active=True,
        )
        try:
            async with typed_session.begin_nested():
                typed_session.add(new_pv)
                await typed_session.flush()
                await typed_session.refresh(new_pv)
            pv = new_pv
        except IntegrityError:
            result = await typed_session.execute(
                select(PromptVersion).where(
                    PromptVersion.name == _LLM_JUDGE_PROMPT_NAME,
                    PromptVersion.is_active == True,  # noqa: E712
                )
            )
            pv = result.scalar_one()

    from app.llm.client import LLMClient  # type: ignore[attr-defined]

    typed_llm: LLMClient = llm  # type: ignore[assignment]

    try:
        response = await typed_llm.complete(
            pv.id,
            inputs={"rubric": assertion.rubric, "document": text},
            response_model=_JudgeScore,
        )
        if response.parsed is None:
            raise RuntimeError("llm_judge: LLM returned no parsed result")
        score = response.parsed.score
        rationale = response.parsed.rationale
        passed = score >= assertion.threshold
        detail = f"score={score:.3f}, threshold={assertion.threshold}, rationale={rationale!r}"
        return AssertionResult(kind="llm_judge", passed=passed, score=score, detail=detail)
    except Exception as exc:
        logger.error("run_llm_judge failed: %s", exc)
        return AssertionResult(
            kind="llm_judge",
            passed=False,
            score=0.0,
            detail=f"error: {exc}",
        )
