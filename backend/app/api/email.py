"""Email sync API endpoints.

Routes
------
POST   /api/email/connect                 Store an OAuth token (dev-mode direct connect).
GET    /api/email/accounts                List current user's connected email accounts.
DELETE /api/email/accounts/{id}           Disconnect an account (token destroyed immediately).
POST   /api/email/accounts/{id}/sync      Run incremental sync for one account.
GET    /api/status-events                 List status events, optionally filtered by state.
POST   /api/status-events/{id}/confirm    Apply a proposed status transition.
POST   /api/status-events/{id}/dismiss    Dismiss a proposed status transition.
GET    /api/status-events/stream          SSE stream of currently-proposed status events.

Privacy notes
-------------
- oauth_token_enc is NEVER returned in any response.
- Disconnect deletes the token immediately (row deletion).
- Tokens are never logged.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.application import Application
from app.db.models.user import User
from app.deps import get_current_user, get_email_provider, get_llm_client, get_token_crypto
from app.email_sync.crypto import TokenCrypto
from app.email_sync.provider import EmailProvider
from app.llm.client import LLMClient
from app.repositories.application import ApplicationRepository
from app.repositories.email import (
    EmailAccountRepository,
    StatusEventRepository,
)
from app.schemas.email import (
    ConnectRequest,
    EmailAccountRead,
    StatusEventRead,
    SyncResult,
)
from app.services.email_sync import sync_account

router = APIRouter(tags=["email"])

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_account_or_404(
    account_id: uuid.UUID,
    user: User,
    repo: EmailAccountRepository,
) -> object:
    """Return the account or raise 404; enforce ownership."""
    account = await repo.get(account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found.",
        )
    return account


async def _get_event_and_app_or_404(
    event_id: uuid.UUID,
    user: User,
    event_repo: StatusEventRepository,
    app_repo: ApplicationRepository,
) -> tuple[object, Application]:
    """Return (event, application) or raise 404; enforce ownership via application.user_id."""
    event = await event_repo.get(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Status event not found.",
        )
    app = await app_repo.get(event.application_id)
    if app is None or app.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Status event not found.",
        )
    return event, app


# ---------------------------------------------------------------------------
# Email account endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/api/email/connect",
    response_model=EmailAccountRead,
    status_code=status.HTTP_201_CREATED,
)
async def connect_email_account(
    body: ConnectRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    crypto: TokenCrypto = Depends(get_token_crypto),  # noqa: B008
) -> EmailAccountRead:
    """Connect an email account by storing an encrypted OAuth token.

    Dev-mode endpoint: the caller supplies the full token bundle directly.

    Real OAuth flow (not implemented here):
        GET  /api/email/connect?provider=gmail → redirect to consent screen
        GET  /api/email/callback?code=…        → exchange code, encrypt, store

    Scopes are recorded as-is from the token bundle's ``scope`` field
    (space-delimited string) or empty list if absent.
    """
    # Encrypt the token — never expose the plaintext after this point
    token_enc: bytes = crypto.encrypt(body.token)

    # Parse scopes from the token bundle if present
    scope_str: str = body.token.get("scope", "")
    scopes: list[str] = scope_str.split() if scope_str else []

    repo = EmailAccountRepository(session)
    account = await repo.create(
        user_id=current_user.id,
        provider=body.provider,
        email_address=body.email_address,
        oauth_token_enc=token_enc,
        scopes=scopes,
    )
    await session.commit()
    await session.refresh(account)
    return EmailAccountRead.model_validate(account)


@router.get("/api/email/accounts", response_model=list[EmailAccountRead])
async def list_email_accounts(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> list[EmailAccountRead]:
    """List all connected email accounts for the current user.

    Tokens are never returned — only safe metadata fields.
    """
    repo = EmailAccountRepository(session)
    accounts = await repo.list_by_user(current_user.id)
    return [EmailAccountRead.model_validate(a) for a in accounts]


@router.delete(
    "/api/email/accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def disconnect_email_account(
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> None:
    """Disconnect and delete an email account.

    Privacy rule: the row (and therefore the encrypted token) is deleted
    immediately on disconnect. No soft-delete or archiving.
    """
    repo = EmailAccountRepository(session)
    account = await _get_account_or_404(account_id, current_user, repo)
    await repo.delete(account)  # type: ignore[arg-type]
    await session.commit()


@router.post(
    "/api/email/accounts/{account_id}/sync",
    response_model=SyncResult,
)
async def sync_email_account(
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> SyncResult:
    """Trigger an incremental email sync for one account.

    Builds the appropriate provider from the stored (encrypted) token and
    runs the INGEST → MATCH → CLASSIFY → GATE → UPDATE pipeline.

    In tests, override get_token_crypto and the route's injected provider
    instead (see tests/api/test_email.py for the pattern used there).
    """
    repo = EmailAccountRepository(session)
    account = await _get_account_or_404(account_id, current_user, repo)

    # Build provider from stored token — token is never exposed
    try:
        provider: EmailProvider = get_email_provider(account)  # type: ignore[arg-type]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to initialize email provider.",
        ) from exc

    counts = await sync_account(session, llm, account, provider)  # type: ignore[arg-type]
    await session.commit()
    return SyncResult(**counts)


# ---------------------------------------------------------------------------
# Status event endpoints
# ---------------------------------------------------------------------------


@router.get("/api/status-events", response_model=list[StatusEventRead])
async def list_status_events(
    state: Literal["proposed", "applied", "dismissed"] | None = Query(default=None),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> list[StatusEventRead]:
    """List status events for the current user, optionally filtered by state.

    When state='proposed', uses the partial index for efficient lookup.
    Other state values perform a full join-filtered query.
    """
    from sqlalchemy import select

    from app.db.models.status_event import StatusEvent

    event_repo = StatusEventRepository(session)

    if state == "proposed" or state is None:
        if state == "proposed":
            events = await event_repo.list_proposed(current_user.id)
        else:
            # All states — join through applications to enforce user ownership
            result = await session.execute(
                select(StatusEvent)
                .join(Application, StatusEvent.application_id == Application.id)
                .where(Application.user_id == current_user.id)
                .order_by(StatusEvent.created_at.asc().nullslast())
            )
            events = list(result.scalars().all())
    else:
        # applied or dismissed — filtered by state + user ownership
        result = await session.execute(
            select(StatusEvent)
            .join(Application, StatusEvent.application_id == Application.id)
            .where(
                Application.user_id == current_user.id,
                StatusEvent.state == state,
            )
            .order_by(StatusEvent.created_at.asc().nullslast())
        )
        events = list(result.scalars().all())

    return [StatusEventRead.model_validate(e) for e in events]


@router.post(
    "/api/status-events/{event_id}/confirm",
    response_model=StatusEventRead,
)
async def confirm_status_event(
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> StatusEventRead:
    """Apply a proposed status transition.

    Updates the application's status to to_status and marks the event as
    'applied'. Idempotent: confirming an already-applied event raises 404
    because it will be owned by the same user but can be re-checked.
    """
    event_repo = StatusEventRepository(session)
    app_repo = ApplicationRepository(session)

    event, app = await _get_event_and_app_or_404(
        event_id, current_user, event_repo, app_repo
    )

    if event.state != "proposed":  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot confirm event in state '{event.state}'.",  # type: ignore[attr-defined]
        )

    # Apply: update application status
    await app_repo.update_status(app, event.to_status)  # type: ignore[attr-defined]

    # Mark event as applied (resolved_at set inside set_state)
    updated_event = await event_repo.set_state(event, "applied")  # type: ignore[arg-type]
    await session.commit()
    return StatusEventRead.model_validate(updated_event)


@router.post(
    "/api/status-events/{event_id}/dismiss",
    response_model=StatusEventRead,
)
async def dismiss_status_event(
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> StatusEventRead:
    """Dismiss a proposed status transition without applying it."""
    event_repo = StatusEventRepository(session)
    app_repo = ApplicationRepository(session)

    event, _ = await _get_event_and_app_or_404(
        event_id, current_user, event_repo, app_repo
    )

    if event.state != "proposed":  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot dismiss event in state '{event.state}'.",  # type: ignore[attr-defined]
        )

    updated_event = await event_repo.set_state(event, "dismissed")  # type: ignore[arg-type]
    await session.commit()
    return StatusEventRead.model_validate(updated_event)


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------


@router.get("/api/status-events/stream")
async def stream_status_events(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    max_iterations: int = Query(default=1, ge=1, le=100),
) -> StreamingResponse:
    """Stream proposed status events as Server-Sent Events.

    Emits one SSE ``data:`` frame per proposed event (JSON-encoded
    StatusEventRead), then a single keep-alive comment, then closes.

    The ``max_iterations`` query parameter controls how many poll cycles are
    executed before the stream closes. It defaults to 1, making the stream
    bounded and easy to test. Set it higher (or poll repeatedly from the client)
    for a longer-lived feed.

    Production note:
        A production implementation would subscribe to a message broker (e.g.
        Redis pub/sub, Kafka) and push events as they arrive instead of polling
        the database. The bounded design here is intentional for testability.
    """
    event_repo = StatusEventRepository(session)
    user_id = current_user.id

    async def _generate() -> AsyncGenerator[str, None]:
        for _ in range(max_iterations):
            events = await event_repo.list_proposed(user_id)
            for ev in events:
                payload = StatusEventRead.model_validate(ev).model_dump(mode="json")
                yield f"data: {json.dumps(payload)}\n\n"

            # Keep-alive comment between iterations (also sent at end of last)
            yield ": keep-alive\n\n"

            if max_iterations > 1:
                await asyncio.sleep(0)  # yield to event loop; real impl would await broker

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
