"""Pydantic schemas for the email sync API.

Privacy rules enforced at the schema layer:
- oauth_token_enc is NEVER included in any response model.
- EmailAccountRead only exposes safe, non-sensitive fields.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class EmailAccountRead(BaseModel):
    """Safe read-only view of an EmailAccount — NEVER includes oauth_token_enc."""

    id: uuid.UUID
    provider: str
    email_address: str
    scopes: list[str]
    status: str
    connected_at: datetime | None
    last_synced_at: datetime | None

    model_config = {"from_attributes": True}


class ConnectRequest(BaseModel):
    """Request body for POST /api/email/connect (dev-mode direct token storage).

    Note on real OAuth flow:
        Production would expose two endpoints:
          GET  /api/email/connect?provider=gmail  → redirect to provider consent screen
          GET  /api/email/callback?code=…         → exchange code for token, store encrypted
        This dev endpoint skips the redirect and stores a token bundle directly,
        which is safe only in a non-public development environment.
    """

    provider: Literal["gmail", "outlook"]
    email_address: str
    token: dict  # full OAuth token bundle (access_token, refresh_token, etc.)


class StatusEventRead(BaseModel):
    """Read-only view of a StatusEvent."""

    id: uuid.UUID
    application_id: uuid.UUID
    from_status: str | None
    to_status: str
    classification: str
    confidence: float
    state: str
    created_at: datetime | None

    model_config = {"from_attributes": True}


class SyncResult(BaseModel):
    """Counts returned from a manual sync trigger."""

    ingested: int
    matched: int
    applied: int
    proposed: int
