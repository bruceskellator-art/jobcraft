"""Data-access layer for email sync models.

Three repositories:
- EmailAccountRepository   — CRUD for email_accounts
- EmailMessageRepository   — create + idempotency check for email_messages
- StatusEventRepository    — create, get, list proposed, set state

Flush-in-repo / commit-in-caller pattern (same as ApplicationRepository).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.email_account import EmailAccount
from app.db.models.email_message import EmailMessage
from app.db.models.status_event import StatusEvent


class EmailAccountRepository:
    """CRUD for EmailAccount rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: uuid.UUID,
        provider: str,
        email_address: str,
        oauth_token_enc: bytes,
        scopes: list[str],
    ) -> EmailAccount:
        """Create a new EmailAccount and flush."""
        account = EmailAccount(
            id=uuid.uuid4(),
            user_id=user_id,
            provider=provider,
            email_address=email_address,
            oauth_token_enc=oauth_token_enc,
            scopes=scopes,
        )
        self._session.add(account)
        await self._session.flush()
        await self._session.refresh(account)
        return account

    async def get(self, account_id: uuid.UUID) -> EmailAccount | None:
        """Return an EmailAccount by primary key, or None."""
        result = await self._session.execute(
            select(EmailAccount).where(EmailAccount.id == account_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[EmailAccount]:
        """Return all EmailAccounts for a user."""
        result = await self._session.execute(
            select(EmailAccount)
            .where(EmailAccount.user_id == user_id)
            .order_by(EmailAccount.connected_at.asc().nullslast())
        )
        return list(result.scalars().all())

    async def update_cursor(
        self,
        account: EmailAccount,
        cursor: str,
    ) -> EmailAccount:
        """Update sync_cursor and last_synced_at, flush and refresh."""
        await self._session.execute(
            update(EmailAccount)
            .where(EmailAccount.id == account.id)
            .values(
                sync_cursor=cursor,
                last_synced_at=datetime.now(UTC),
            )
        )
        await self._session.flush()
        await self._session.refresh(account)
        return account

    async def set_status(
        self,
        account: EmailAccount,
        status: Literal["active", "paused", "reauth_required", "revoked"],
    ) -> EmailAccount:
        """Update the account status, flush and refresh."""
        await self._session.execute(
            update(EmailAccount)
            .where(EmailAccount.id == account.id)
            .values(status=status)
        )
        await self._session.flush()
        await self._session.refresh(account)
        return account

    async def delete(self, account: EmailAccount) -> None:
        """Delete an EmailAccount (and its token) immediately.

        Privacy rule: disconnect deletes the token immediately.
        """
        await self._session.delete(account)
        await self._session.flush()


class EmailMessageRepository:
    """Create + idempotency-check for EmailMessage rows.

    Privacy rule: only matched messages are persisted (metadata + snippet only;
    full body is NEVER stored).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_provider_id(
        self,
        email_account_id: uuid.UUID,
        provider_message_id: str,
    ) -> EmailMessage | None:
        """Return an existing EmailMessage by (account, provider_message_id), or None.

        Used for idempotency: if the message was already processed on a
        previous sync run we skip it.
        """
        result = await self._session.execute(
            select(EmailMessage).where(
                EmailMessage.email_account_id == email_account_id,
                EmailMessage.provider_message_id == provider_message_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        email_account_id: uuid.UUID,
        application_id: uuid.UUID,
        provider_message_id: str,
        thread_id: str | None,
        from_address: str,
        from_domain: str,
        subject: str | None,
        snippet: str | None,
        received_at: datetime,
        match_method: str | None,
        match_confidence: float | None,
    ) -> EmailMessage:
        """Persist message metadata + snippet. Full body is NEVER stored here."""
        msg = EmailMessage(
            id=uuid.uuid4(),
            email_account_id=email_account_id,
            application_id=application_id,
            provider_message_id=provider_message_id,
            thread_id=thread_id,
            from_address=from_address,
            from_domain=from_domain,
            subject=subject,
            snippet=snippet,
            received_at=received_at,
            match_method=match_method,
            match_confidence=match_confidence,
        )
        self._session.add(msg)
        await self._session.flush()
        await self._session.refresh(msg)
        return msg


class StatusEventRepository:
    """CRUD for StatusEvent rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        application_id: uuid.UUID,
        email_message_id: uuid.UUID | None,
        from_status: str | None,
        to_status: str,
        classification: str,
        confidence: float,
        state: Literal["proposed", "applied", "dismissed"],
        prompt_version_id: uuid.UUID | None = None,
    ) -> StatusEvent:
        """Create a new StatusEvent and flush."""
        event = StatusEvent(
            id=uuid.uuid4(),
            application_id=application_id,
            email_message_id=email_message_id,
            from_status=from_status,
            to_status=to_status,
            classification=classification,
            confidence=confidence,
            state=state,
            prompt_version_id=prompt_version_id,
        )
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)
        return event

    async def list_proposed(self, user_id: uuid.UUID) -> list[StatusEvent]:
        """Return all proposed (pending) StatusEvents for a user's applications.

        Uses the partial index on state='proposed' for efficient lookup.
        """
        from app.db.models.application import Application

        result = await self._session.execute(
            select(StatusEvent)
            .join(Application, StatusEvent.application_id == Application.id)
            .where(
                Application.user_id == user_id,
                StatusEvent.state == "proposed",
            )
            .order_by(StatusEvent.created_at.asc().nullslast())
        )
        return list(result.scalars().all())

    async def get(self, event_id: uuid.UUID) -> StatusEvent | None:
        """Return a StatusEvent by primary key, or None."""
        result = await self._session.execute(
            select(StatusEvent).where(StatusEvent.id == event_id)
        )
        return result.scalar_one_or_none()

    async def set_state(
        self,
        event: StatusEvent,
        state: Literal["proposed", "applied", "dismissed"],
    ) -> StatusEvent:
        """Update state (and resolved_at if terminal), flush and refresh."""
        values: dict[str, object] = {"state": state}
        if state in ("applied", "dismissed"):
            values["resolved_at"] = datetime.now(UTC)

        await self._session.execute(
            update(StatusEvent)
            .where(StatusEvent.id == event.id)
            .values(**values)
        )
        await self._session.flush()
        await self._session.refresh(event)
        return event
