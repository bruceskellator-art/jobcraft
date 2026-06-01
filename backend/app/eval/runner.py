"""Eval suite runner: generate artifacts, run assertions, persist EvalRun.

Concurrency model (session-safe):
- Cases run CONCURRENTLY via asyncio.gather.
- Each case gets its OWN AsyncSession from the session factory, so no two
  coroutines ever touch the same session at once (safe on real asyncpg).
- WITHIN a case, assertions run SEQUENTIALLY because the LLM-backed ones
  (groundedness, llm_judge) write llm_calls rows to that case's session;
  concurrent access to a single session is unsafe.
- The EvalRun is persisted on a SEPARATE final session after all cases finish.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.eval_run import EvalRun
from app.eval.assertions import (
    run_contains_skill,
    run_excludes_phrase,
    run_groundedness,
    run_length,
    run_llm_judge,
)
from app.eval.types import (
    AssertionResult,
    CaseResult,
    ContainsSkillAssertion,
    EvalCase,
    EvalSuite,
    ExcludesPhraseAssertion,
    GroundednessAssertion,
    LengthAssertion,
    LlmJudgeAssertion,
)
from app.llm.client import LLMClient

logger = logging.getLogger(__name__)

# Builds an LLMClient bound to a specific (per-case) session.
LLMFactory = Callable[[AsyncSession], LLMClient]

# Root of the eval/ directory relative to the repo root.
_EVAL_ROOT = Path(__file__).resolve().parents[3] / "eval"


def _resolve_fixture(path_str: str | None) -> Path | None:
    """Resolve a fixture path string relative to eval/ root."""
    if path_str is None:
        return None
    return _EVAL_ROOT / path_str


async def _run_assertion(
    assertion_def: object,
    text: str,
    *,
    session: AsyncSession,
    llm: LLMClient,
    experience_items: list,
) -> AssertionResult:
    """Dispatch to the appropriate assertion runner. Never raises."""
    try:
        if isinstance(assertion_def, ContainsSkillAssertion):
            return run_contains_skill(assertion_def, text)
        if isinstance(assertion_def, ExcludesPhraseAssertion):
            return run_excludes_phrase(assertion_def, text)
        if isinstance(assertion_def, LengthAssertion):
            return run_length(assertion_def, text)
        if isinstance(assertion_def, GroundednessAssertion):
            return await run_groundedness(
                assertion_def,
                text,
                session=session,
                llm=llm,
                experience_items=experience_items,
            )
        if isinstance(assertion_def, LlmJudgeAssertion):
            return await run_llm_judge(assertion_def, text, session=session, llm=llm)
        return AssertionResult(
            kind=str(getattr(assertion_def, "kind", "unknown")),
            passed=False,
            score=None,
            detail=f"unknown assertion type: {type(assertion_def).__name__}",
        )
    except Exception as exc:
        logger.error("_run_assertion error (%s): %s", getattr(assertion_def, "kind", "?"), exc)
        return AssertionResult(
            kind=str(getattr(assertion_def, "kind", "unknown")),
            passed=False,
            score=None,
            detail=f"runner error: {exc}",
        )


async def _build_case_inputs(
    case: EvalCase,
    session: AsyncSession,
) -> tuple[uuid.UUID, list, object]:
    """Materialize ephemeral User/ExperienceItem/JobPosting rows for a case.

    Returns (user_id, experience_items, job).
    """
    from app.db.models.experience_item import ExperienceItem
    from app.db.models.job_posting import JobPosting
    from app.db.models.user import User
    from app.eval.loader import load_fixture_json

    experience_items: list[ExperienceItem] = []
    user_id = uuid.uuid4()
    ephemeral_user = User(
        id=user_id, email=f"eval-{user_id}@jobcraft.local", name="Eval User"
    )
    session.add(ephemeral_user)
    await session.flush()

    if case.user_corpus is not None:
        corpus_data = load_fixture_json(_resolve_fixture(case.user_corpus))  # type: ignore[arg-type]
        for item_data in corpus_data.get("experience_items", []):
            item = ExperienceItem(
                id=uuid.uuid4(),
                user_id=user_id,
                kind=item_data.get("kind", "work"),
                title=item_data.get("title"),
                organization=item_data.get("organization"),
                content=item_data.get("content", ""),
                tags=item_data.get("tags", []),
            )
            session.add(item)
            experience_items.append(item)
    else:
        fallback = ExperienceItem(
            id=uuid.uuid4(),
            user_id=user_id,
            kind="work",
            title="Software Engineer",
            content="General software engineering experience.",
        )
        session.add(fallback)
        experience_items.append(fallback)
    await session.flush()

    if case.job is not None:
        job_data = load_fixture_json(_resolve_fixture(case.job))  # type: ignore[arg-type]
        job = JobPosting(
            id=uuid.uuid4(),
            source=job_data.get("source", "eval"),
            source_url=job_data.get("source_url", "https://eval.example.com"),
            source_id=job_data.get("source_id", str(uuid.uuid4())),
            company=job_data.get("company", "Eval Corp"),
            title=job_data.get("title", "Software Engineer"),
            raw_content=job_data.get("raw_content", ""),
            extracted=job_data.get("extracted"),
        )
    else:
        job = JobPosting(
            id=uuid.uuid4(),
            source="eval",
            source_url="https://eval.example.com",
            source_id=str(uuid.uuid4()),
            company="Eval Corp",
            title="Software Engineer",
            raw_content="General software engineering role.",
            extracted=None,
        )
    session.add(job)
    await session.flush()

    return user_id, experience_items, job


async def _run_case(
    case: EvalCase,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    llm_factory: LLMFactory,
    embed: object,
    store: object,
) -> CaseResult:
    """Run a single case inside its OWN session.

    Generation + all assertions execute sequentially on that one session so
    no concurrent single-session access occurs.
    """
    from app.generator.service import generate_resume
    from app.generator.types import StyleConfig

    async with session_factory() as session:
        llm = llm_factory(session)
        try:
            user_id, experience_items, job = await _build_case_inputs(case, session)
            generated_text, items_used = await generate_resume(
                session,
                llm,
                embed,  # type: ignore[arg-type]
                store,  # type: ignore[arg-type]
                user_id,
                job,  # type: ignore[arg-type]
                StyleConfig(),
                items=experience_items,
            )
        except Exception as exc:
            logger.error("_run_case %s: generation failed: %s", case.id, exc)
            return CaseResult(
                case_id=case.id,
                passed=False,
                score=0.0,
                assertions=[
                    AssertionResult(
                        kind="generation",
                        passed=False,
                        score=0.0,
                        detail=f"generation error: {exc}",
                    )
                ],
            )

        # Assertions run SEQUENTIALLY — LLM-backed ones write to this session.
        assertion_results: list[AssertionResult] = []
        for a in case.assertions:
            result = await _run_assertion(
                a,
                generated_text,
                session=session,
                llm=llm,
                experience_items=items_used,
            )
            assertion_results.append(result)

        # Commit the case's own session (llm_calls rows etc.) before it closes.
        await session.commit()

    passed = all(r.passed for r in assertion_results)
    scores = [r.score for r in assertion_results if r.score is not None]
    mean_score = sum(scores) / len(scores) if scores else None

    return CaseResult(
        case_id=case.id,
        passed=passed,
        score=mean_score,
        assertions=assertion_results,
    )


def _compute_aggregate(case_results: list[CaseResult]) -> dict[str, float]:
    """Compute aggregate pass rate and mean score per assertion kind."""
    if not case_results:
        return {"pass_rate": 0.0}

    total_cases = len(case_results)
    passed_cases = sum(1 for c in case_results if c.passed)
    aggregate: dict[str, float] = {"pass_rate": passed_cases / total_cases}

    # Collect scores by kind
    kind_scores: dict[str, list[float]] = {}
    for cr in case_results:
        for ar in cr.assertions:
            if ar.score is not None:
                kind_scores.setdefault(ar.kind, []).append(ar.score)

    for kind, scores in kind_scores.items():
        aggregate[f"{kind}_mean_score"] = sum(scores) / len(scores)

    return aggregate


async def run_suite(
    session_factory: async_sessionmaker[AsyncSession],
    suite: EvalSuite,
    *,
    prompt_version_id: uuid.UUID,
    llm_factory: LLMFactory,
    embed: object,
    store: object,
) -> EvalRun:
    """Run all cases in a suite, persist an EvalRun, and return it.

    Cases run concurrently, each on its own session from ``session_factory``.
    The EvalRun is persisted on a separate, final session.

    Failing cases/assertions are recorded — the run never crashes.
    """
    started_at = datetime.now(tz=UTC)

    case_tasks = [
        _run_case(
            case,
            session_factory=session_factory,
            llm_factory=llm_factory,
            embed=embed,
            store=store,
        )
        for case in suite.cases
    ]
    case_results: list[CaseResult] = list(await asyncio.gather(*case_tasks))

    aggregate = _compute_aggregate(case_results)
    completed_at = datetime.now(tz=UTC)

    eval_run = EvalRun(
        id=uuid.uuid4(),
        suite_name=suite.name,
        prompt_version_id=prompt_version_id,
        results=[cr.model_dump() for cr in case_results],
        aggregate_scores=aggregate,
        started_at=started_at,
        completed_at=completed_at,
    )

    async with session_factory() as persist_session:
        persist_session.add(eval_run)
        await persist_session.commit()
        await persist_session.refresh(eval_run)

    return eval_run
