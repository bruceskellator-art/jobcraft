"""Apply orchestration service (Phase 6, §4.8).

Coordinates the full apply pipeline:
1. enqueue_applications  — get-or-create queued Applications for a job list.
2. process_application   — run one Application through strategy → map → gate → record.
3. run_queue             — batch-process queued Applications with per-app savepoints.

SAFETY INVARIANTS (never relaxed):
- dry_run defaults to True; forms are NEVER auto-submitted without explicit opt-in.
- BLOCK decisions are never bypassed.
- Daily cap is enforced before submitting; cap breach forces REVIEW with a clear reason.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.apply.browser import FormSource
from app.apply.gate import decide
from app.apply.strategies import ApplyStrategy, select_strategy
from app.apply.types import ALLOWED_MANUAL_STATUSES, KNOCKOUT_KEYS, FieldMap, GateDecision
from app.db.models.application import Application
from app.db.models.application_attempt import ApplicationAttempt
from app.embeddings.base import EmbeddingClient
from app.repositories.application import ApplicationAttemptRepository, ApplicationRepository
from app.repositories.job import JobRepository
from app.services.autopilot import AutopilotConfig
from app.vectorstore.base import VectorStore

if TYPE_CHECKING:
    from app.llm.client import LLMClient

logger = logging.getLogger(__name__)

# Re-export for callers that import the constant from this module.
_ALLOWED_MANUAL_STATUSES = ALLOWED_MANUAL_STATUSES


async def enqueue_applications(
    session: AsyncSession,
    user_id: uuid.UUID,
    job_ids: list[uuid.UUID],
) -> list[Application]:
    """Get-or-create queued Applications for the given job IDs.

    Deduplicates: if an Application for (user_id, job_id) already exists it is
    returned unchanged regardless of its current status.
    """
    repo = ApplicationRepository(session)
    results: list[Application] = []
    for job_id in job_ids:
        app = await repo.enqueue(user_id, job_id)
        results.append(app)
    return results


async def process_application(
    session: AsyncSession,
    llm: LLMClient | None,
    embed: EmbeddingClient,
    store: VectorStore,
    user_id: uuid.UUID,
    app: Application,
    *,
    strategies: list[ApplyStrategy],
    form_source: FormSource,
    autopilot: AutopilotConfig,
    dry_run: bool = True,
) -> ApplicationAttempt:
    """Run a single Application through the full apply pipeline.

    Steps:
    1. Look up the job and latest match score.
    2. Select strategy and render form fields.
    3. Detect captcha (from form_source outcome) and unresolved knockouts.
    4. map_fields via the selected strategy's fill().
    5. gate.decide() with all signals.
    6. Enforce daily cap — if exceeded, force REVIEW.
    7. Write ApplicationAttempt and update Application.status.

    Per-application exceptions bubble up to run_queue which isolates them.
    """
    app_repo = ApplicationRepository(session)
    attempt_repo = ApplicationAttemptRepository(session)
    job_repo = JobRepository(session)

    job = await job_repo.get(app.job_id)
    if job is None:
        raise ValueError(f"JobPosting {app.job_id} not found for application {app.id}")

    # Fetch latest match score (None = unknown, treated conservatively by gate).
    # MatchRepository.get requires prompt_version_id; use a list query instead.
    from sqlalchemy import select as sa_select

    from app.db.models.match import Match

    match_result = await session.execute(
        sa_select(Match)
        .where(Match.user_id == user_id, Match.job_id == job.id)
        .order_by(Match.id.desc())
        .limit(1)
    )
    latest_match = match_result.scalar_one_or_none()
    match_score: float | None = latest_match.overall_score if latest_match is not None else None

    # Step 1: render the form to detect captcha BEFORE mapping or submitting.
    captcha: bool = await form_source.has_captcha(job, app)

    # Step 2: if captcha is detected the gate will BLOCK regardless; still
    # map fields (for attempt logging) but gate prevents submission.

    # Select strategy and fill the form.
    strategy = select_strategy(job, strategies)
    field_map: FieldMap = await strategy.fill(
        app,
        job,
        session,
        llm,
        embed,
        store,
        user_id,
    )

    # Detect unresolved knockouts: a field is knockout if is_knockout flag OR
    # its name matches a canonical KNOCKOUT_KEY — mirrors field_mapper._is_knockout.
    has_unresolved_knockout = any(
        (mf.field.is_knockout or mf.field.name.lower() in KNOCKOUT_KEYS)
        and mf.value is None
        for mf in field_map.fields
    )

    # Enforce daily cap BEFORE the gate so it overrides AUTO_SUBMIT.
    # NOTE: under concurrent arq workers this COUNT is not lock-protected; a
    # distributed lock (Redis INCR or SELECT FOR UPDATE) is required for true
    # cap enforcement at scale — TODO for production.
    daily_count = await app_repo.count_submitted_today(user_id)
    cap_exceeded = daily_count >= autopilot.daily_cap

    if cap_exceeded:
        gate = _forced_review(
            f"Daily cap of {autopilot.daily_cap} total submissions reached for today."
        )
    else:
        gate = decide(
            field_map,
            job,
            autopilot=autopilot,
            match_score=match_score,
            source=job.source,
            captcha=captcha,
            has_unresolved_knockout=has_unresolved_knockout,
        )

    # Determine outcome and perform submission if warranted.
    outcome_str: str
    blocked_reason: str | None = None
    screenshot_path: str | None = None
    apply_mode: str | None = None

    if gate.decision == "block":
        outcome_str = "blocked"
        blocked_reason = gate.reason
        await app_repo.update_status(
            app,
            "blocked",
            blocked_reason=blocked_reason,
        )

    elif gate.decision == "review":
        outcome_str = "queued"  # attempt outcome is 'queued' (awaiting human)
        await app_repo.update_status(app, "needs_review")

    else:  # auto_submit
        if dry_run:
            outcome_str = "queued"
            apply_mode = "auto"
            await app_repo.update_status(
                app,
                "auto_filling",
                apply_mode=apply_mode,
                apply_confidence=field_map.overall_confidence,
            )
        else:
            apply_outcome = await strategy.submit(job, field_map)
            if apply_outcome.outcome == "submitted":
                outcome_str = "submitted"
                apply_mode = "auto"
                screenshot_path = apply_outcome.screenshot_path
                await app_repo.update_status(
                    app,
                    "submitted",
                    apply_mode=apply_mode,
                    apply_confidence=field_map.overall_confidence,
                    submitted_at=datetime.now(UTC),
                )
            elif apply_outcome.outcome == "blocked":
                outcome_str = "blocked"
                blocked_reason = apply_outcome.blocked_reason
                screenshot_path = apply_outcome.screenshot_path
                await app_repo.update_status(
                    app,
                    "blocked",
                    blocked_reason=blocked_reason,
                )
            else:
                outcome_str = "failed"
                await app_repo.update_status(app, "failed")

    # Serialize field_map to a JSON-safe list for storage.
    field_map_data = [
        {
            "name": mf.field.name,
            "label": mf.field.label,
            "field_type": mf.field.field_type,
            "is_knockout": mf.field.is_knockout,
            "value": mf.value,
            "source": mf.source,
            "confidence": mf.confidence,
        }
        for mf in field_map.fields
    ]

    attempt = await attempt_repo.create(
        application_id=app.id,
        strategy=strategy.name,
        field_map=field_map_data,
        overall_confidence=field_map.overall_confidence,
        outcome=outcome_str,
        blocked_reason=blocked_reason,
        screenshot_path=screenshot_path,
    )

    return attempt


async def run_queue(
    session: AsyncSession,
    llm: LLMClient | None,
    embed: EmbeddingClient,
    store: VectorStore,
    user_id: uuid.UUID,
    *,
    strategies: list[ApplyStrategy],
    form_source: FormSource,
    dry_run: bool = True,
    limit: int = 50,
) -> dict[str, int]:
    """Batch-process queued Applications for user_id.

    Per-app failures are isolated (savepoint pattern); a single bad app does not
    abort the batch.  Returns counts: {submitted, needs_review, blocked, failed}.
    """
    app_repo = ApplicationRepository(session)
    autopilot_svc = await _load_autopilot(session, user_id)

    queued = await app_repo.list_by_user(user_id, status="queued")
    queued = queued[:limit]

    counts: dict[str, int] = {
        "submitted": 0,
        "needs_review": 0,
        "blocked": 0,
        "failed": 0,
    }

    for app in queued:
        try:
            async with session.begin_nested():  # savepoint
                attempt = await process_application(
                    session,
                    llm,
                    embed,
                    store,
                    user_id,
                    app,
                    strategies=strategies,
                    form_source=form_source,
                    autopilot=autopilot_svc,
                    dry_run=dry_run,
                )
                outcome = attempt.outcome
                if outcome == "submitted":
                    counts["submitted"] += 1
                elif outcome == "queued":
                    # gate said review OR dry_run auto_filling — both surface as needs_review
                    await session.refresh(app)
                    if app.status == "needs_review":
                        counts["needs_review"] += 1
                    # auto_filling (dry_run=True auto_submit) doesn't count in any bucket
                elif outcome == "blocked":
                    counts["blocked"] += 1
                else:
                    counts["failed"] += 1
        except Exception:
            logger.exception(
                "process_application failed for application %s — skipping",
                app.id,
            )
            counts["failed"] += 1

    return counts


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _forced_review(reason: str) -> GateDecision:
    """Return a GateDecision forcing manual review."""
    return GateDecision(decision="review", reason=reason)


async def _load_autopilot(session: AsyncSession, user_id: uuid.UUID) -> AutopilotConfig:
    from app.services.autopilot import get_autopilot_config

    return await get_autopilot_config(session, user_id)
