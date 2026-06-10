"""Email provider abstraction layer.

Defines the EmailProvider protocol and concrete implementations:
- GmailProvider   — thin stub; lazy-imports google-api-python-client
- OutlookProvider — thin stub; lazy-imports msal
- FakeEmailProvider — deterministic in-memory provider for tests

Privacy rules:
- Read-only OAuth scopes only (gmail.readonly / Mail.Read). No send/modify ever.
- Incremental sync via historyId (Gmail) or deltaLink (Graph).
- Providers return RawEmail objects; callers decide what to persist.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class RawEmail:
    """Immutable value object representing a single email fetched from a provider."""

    provider_message_id: str
    thread_id: str | None
    from_address: str
    subject: str | None
    snippet: str | None
    body: str
    received_at: datetime


class EmailProvider(Protocol):
    """Protocol every email provider must satisfy."""

    name: str

    async def list_since(
        self, cursor: str | None
    ) -> tuple[list[RawEmail], str]:
        """Fetch new messages since *cursor*.

        Args:
            cursor: Provider-specific incremental sync token (historyId /
                    deltaLink). None means first-run / full backfill.

        Returns:
            A tuple of (list[RawEmail], new_cursor). The new cursor should be
            stored in email_accounts.sync_cursor after a successful sync.
        """
        ...


class GmailProvider:
    """Gmail read-only provider using Gmail API historyId for incremental sync.

    OAuth scope required: gmail.readonly (read-only — we NEVER request
    gmail.modify, gmail.send, or any write scope).

    Incremental sync strategy:
    - First sync: list messages since the user's earliest submitted_at,
      store the returned historyId as sync_cursor.
    - Subsequent syncs: call users.history.list(startHistoryId=cursor) to get
      only new/changed message IDs, then batch-fetch the messages.

    Note: This is a THIN STUB. The real driver is not wired in this build.
    Lazy-import google-api-python-client so the package imports without it.
    """

    name = "gmail"

    def __init__(self, access_token: str) -> None:
        self._access_token = access_token

    async def list_since(
        self, cursor: str | None
    ) -> tuple[list[RawEmail], str]:  # pragma: no cover
        try:
            import googleapiclient  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "google-api-python-client is required for GmailProvider. "
                "Install it with: pip install google-api-python-client"
            ) from exc

        raise NotImplementedError(
            "GmailProvider driver is not wired in this build. "
            "Implement list_since using gmail.readonly scope + historyId."
        )


class OutlookProvider:
    """Microsoft Graph / Outlook read-only provider using deltaLink for incremental sync.

    OAuth scope required: Mail.Read (read-only — we NEVER request
    Mail.ReadWrite, Mail.Send, or any write scope).

    Incremental sync strategy:
    - First sync: GET /me/mailFolders/inbox/messages with $deltatoken=latest
      to get a deltaLink cursor.
    - Subsequent syncs: follow the deltaLink URL to fetch only new/changed
      messages since last sync.

    Note: This is a THIN STUB. The real driver is not wired in this build.
    Lazy-import msal so the package imports without it.
    """

    name = "outlook"

    def __init__(self, access_token: str) -> None:
        self._access_token = access_token

    async def list_since(
        self, cursor: str | None
    ) -> tuple[list[RawEmail], str]:  # pragma: no cover
        try:
            import msal  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "msal is required for OutlookProvider. "
                "Install it with: pip install msal"
            ) from exc

        raise NotImplementedError(
            "OutlookProvider driver is not wired in this build. "
            "Implement list_since using Mail.Read scope + Graph deltaLink."
        )


class FakeEmailProvider:
    """Deterministic in-memory provider for tests and local development.

    Args:
        messages: Canned list of RawEmail objects to return on the first call.
        cursor: The cursor value to return as the new sync_cursor.
    """

    name = "fake"

    def __init__(self, messages: list[RawEmail], cursor: str = "cursor-v1") -> None:
        self._messages = list(messages)
        self._cursor = cursor
        self.call_count = 0

    async def list_since(
        self, cursor: str | None
    ) -> tuple[list[RawEmail], str]:
        self.call_count += 1
        return list(self._messages), self._cursor
