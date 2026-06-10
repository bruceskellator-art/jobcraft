from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailAccount(Base):
    __tablename__ = "email_accounts"
    __table_args__ = (
        sa.CheckConstraint(
            "provider IN ('gmail', 'outlook')",
            name="email_accounts_provider_check",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'reauth_required', 'revoked')",
            name="email_accounts_status_check",
        ),
        sa.UniqueConstraint(
            "user_id",
            "email_address",
            name="uq_email_accounts_user_email",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(sa.Text, nullable=False)
    email_address: Mapped[str] = mapped_column(sa.Text, nullable=False)
    oauth_token_enc: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()).with_variant(sa.JSON(), "sqlite"),
        default=list,
        server_default="{}",
    )
    sync_cursor: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    watch_expires_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    connected_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    last_synced_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        sa.Text, nullable=False, server_default="active"
    )
