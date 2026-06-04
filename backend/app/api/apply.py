"""Apply API router (Phase 6, §4.8).

Routes
------
POST /api/apply/queue               Enqueue jobs for a user → list[ApplicationRead]
GET  /api/applications              List applications (optional ?status filter)
GET  /api/apply/queue               Applications needing review, with field maps
POST /api/applications/{id}/process Process one application now
POST /api/applications/{id}/approve User approves reviewed field map → submit
PATCH /api/applications/{id}/status Manual status change (Kanban)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.apply.browser import FormSource
from app.apply.strategies import ApplyStrategy
from app.db.base import get_session
from app.db.models.user import User
from app.deps import (
    get_apply_strategies,
    get_current_user,
    get_embedding_client,
    get_form_source,
    get_llm_client,
    get_vector_store,
)
from app.embeddings.base import EmbeddingClient
from app.llm.client import LLMClient
from app.repositories.application import ApplicationAttemptRepository, ApplicationRepository
from app.repositories.job import JobRepository
from app.schemas.apply import (
    ApplicationAttemptRead,
    ApplicationRead,
    ApplyQueueItem,
    EnqueueRequest,
    FieldMapView,
    JobSummary,
    MappedFieldView,
    RunQueueRequest,
    StatusUpdateRequest,
)
from app.services.apply_orchestration import enqueue_applications, process_application
from app.services.autopilot import get_autopilot_config
from app.vectorstore.base import VectorStore

router = APIRouter(tags=["apply"])

# Statuses that may be set via the manual PATCH endpoint.
_ALLOWED_MANUAL_STATUSES = frozenset(
    {
        "interested",
        "queued",
        "needs_review",
        "phone_screen",
        "technical",
        "onsite",
        "offer",
        "rejected",
        "withdrawn",
    }
)


# ---------------------------------------------------------------------------
# POST /api/apply/queue
# ---------------------------------------------------------------------------


@router.post("/api/apply/queue", response_model=list[ApplicationRead])
async def queue_applications(
    body: EnqueueRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> list[ApplicationRead]:
    """Enqueue a list of jobs for the current user.

    Returns get-or-created Application objects (deduped by (user_id, job_id)).
    """
    apps = await enqueue_applications(session, current_user.id, body.job_ids)
    await session.commit()
    return [ApplicationRead.model_validate(a) for a in apps]


# ---------------------------------------------------------------------------
# GET /api/applications
# ---------------------------------------------------------------------------


@router.get("/api/applications", response_model=list[ApplicationRead])
async def list_applications(
    status: str | None = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> list[ApplicationRead]:
    """List all applications for the current user, optionally filtered by status."""
    repo = ApplicationRepository(session)
    apps = await repo.list_by_user(current_user.id, status=status)
    return [ApplicationRead.model_validate(a) for a in apps]


# ---------------------------------------------------------------------------
# GET /api/apply/queue
# ---------------------------------------------------------------------------


@router.get("/api/apply/queue", response_model=list[ApplyQueueItem])
async def get_review_queue(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> list[ApplyQueueItem]:
    """Return applications in 'needs_review' status with their latest field maps."""
    app_repo = ApplicationRepository(session)
    attempt_repo = ApplicationAttemptRepository(session)
    job_repo = JobRepository(session)

    apps = await app_repo.list_by_user(current_user.id, status="needs_review")

    items: list[ApplyQueueItem] = []
    for app in apps:
        job = await job_repo.get(app.job_id)
        if job is None:
            continue

        latest_attempt = await attempt_repo.latest_for(app.id)
        field_map_view: FieldMapView | None = None
        if latest_attempt is not None and isinstance(latest_attempt.field_map, list):
            mapped_fields = [
                MappedFieldView(
                    name=f.get("name", ""),
                    label=f.get("label", ""),
                    value=f.get("value"),
                    source=f.get("source", "none"),
                    confidence=f.get("confidence", 0.0),
                )
                for f in latest_attempt.field_map
                if isinstance(f, dict)
            ]
            total = sum(mf.confidence for mf in mapped_fields)
            overall = total / len(mapped_fields) if mapped_fields else 0.0
            field_map_view = FieldMapView(fields=mapped_fields, overall_confidence=overall)

        items.append(
            ApplyQueueItem(
                application=ApplicationRead.model_validate(app),
                job=JobSummary(
                    id=job.id,
                    title=job.title,
                    company=job.company,
                    source=job.source,
                ),
                field_map=field_map_view,
            )
        )

    return items


# ---------------------------------------------------------------------------
# POST /api/applications/{id}/process
# ---------------------------------------------------------------------------


@router.post("/api/applications/{application_id}/process", response_model=ApplicationAttemptRead)
async def process_one(
    application_id: uuid.UUID,
    body: RunQueueRequest = RunQueueRequest(),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
    embed: EmbeddingClient = Depends(get_embedding_client),  # noqa: B008
    store: VectorStore = Depends(get_vector_store),  # noqa: B008
    form_source: FormSource = Depends(get_form_source),  # noqa: B008
    strategies: list[ApplyStrategy] = Depends(get_apply_strategies),  # noqa: B008
) -> ApplicationAttemptRead:
    """Process a single application immediately (dry_run=True by default)."""
    app_repo = ApplicationRepository(session)
    app = await app_repo.get(application_id)
    if app is None or app.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    autopilot = await get_autopilot_config(session, current_user.id)
    attempt = await process_application(
        session,
        llm,
        embed,
        store,
        current_user.id,
        app,
        strategies=strategies,
        form_source=form_source,
        autopilot=autopilot,
        dry_run=body.dry_run,
    )
    await session.commit()
    return ApplicationAttemptRead.model_validate(attempt)


# ---------------------------------------------------------------------------
# POST /api/applications/{id}/approve
# ---------------------------------------------------------------------------


@router.post("/api/applications/{application_id}/approve", response_model=ApplicationRead)
async def approve_application(
    application_id: uuid.UUID,
    body: RunQueueRequest = RunQueueRequest(),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
    embed: EmbeddingClient = Depends(get_embedding_client),  # noqa: B008
    store: VectorStore = Depends(get_vector_store),  # noqa: B008
    form_source: FormSource = Depends(get_form_source),  # noqa: B008
    strategies: list[ApplyStrategy] = Depends(get_apply_strategies),  # noqa: B008
) -> ApplicationRead:
    """User approves the reviewed field map and triggers submission.

    Re-runs process_application with dry_run=False (or honoring body.dry_run).
    The gate is re-evaluated; a BLOCK at this stage still prevents submission.
    """
    app_repo = ApplicationRepository(session)
    app = await app_repo.get(application_id)
    if app is None or app.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    autopilot = await get_autopilot_config(session, current_user.id)
    await process_application(
        session,
        llm,
        embed,
        store,
        current_user.id,
        app,
        strategies=strategies,
        form_source=form_source,
        autopilot=autopilot,
        dry_run=body.dry_run,
    )
    await session.refresh(app)
    await session.commit()
    return ApplicationRead.model_validate(app)


# ---------------------------------------------------------------------------
# PATCH /api/applications/{id}/status
# ---------------------------------------------------------------------------


@router.patch("/api/applications/{application_id}/status", response_model=ApplicationRead)
async def update_status(
    application_id: uuid.UUID,
    body: StatusUpdateRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ApplicationRead:
    """Manually update the status of an application (Kanban board moves).

    Only status values in _ALLOWED_MANUAL_STATUSES are accepted.
    Ownership is enforced — 404 if the application belongs to another user.
    """
    if body.status not in _ALLOWED_MANUAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Status '{body.status}' is not allowed via this endpoint. "
                f"Allowed: {sorted(_ALLOWED_MANUAL_STATUSES)}"
            ),
        )

    app_repo = ApplicationRepository(session)
    app = await app_repo.get(application_id)
    if app is None or app.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    updated = await app_repo.update_status(app, body.status)
    await session.commit()
    return ApplicationRead.model_validate(updated)
