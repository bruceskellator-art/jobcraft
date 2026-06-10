"""Phase 8 tables: email_accounts, email_messages, status_events

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-24

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.Text,
            sa.CheckConstraint(
                "provider IN ('gmail', 'outlook')",
                name="email_accounts_provider_check",
            ),
            nullable=False,
        ),
        sa.Column("email_address", sa.Text, nullable=False),
        sa.Column("oauth_token_enc", sa.LargeBinary, nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("sync_cursor", sa.Text, nullable=True),
        sa.Column("watch_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "connected_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Text,
            sa.CheckConstraint(
                "status IN ('active', 'paused', 'reauth_required', 'revoked')",
                name="email_accounts_status_check",
            ),
            nullable=False,
            server_default="active",
        ),
        sa.UniqueConstraint(
            "user_id",
            "email_address",
            name="uq_email_accounts_user_email",
        ),
    )

    op.create_table(
        "email_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "email_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("email_accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id"),
            nullable=True,
        ),
        sa.Column("provider_message_id", sa.Text, nullable=False),
        sa.Column("thread_id", sa.Text, nullable=True),
        sa.Column("from_address", sa.Text, nullable=False),
        sa.Column("from_domain", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=True),
        sa.Column("snippet", sa.Text, nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("match_method", sa.Text, nullable=True),
        sa.Column("match_confidence", sa.Float, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "email_account_id",
            "provider_message_id",
            name="uq_email_messages_account_msg",
        ),
    )

    op.create_table(
        "status_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id"),
            nullable=False,
        ),
        sa.Column(
            "email_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("email_messages.id"),
            nullable=True,
        ),
        sa.Column("from_status", sa.Text, nullable=True),
        sa.Column("to_status", sa.Text, nullable=False),
        sa.Column("classification", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column(
            "state",
            sa.Text,
            sa.CheckConstraint(
                "state IN ('proposed', 'applied', 'dismissed')",
                name="status_events_state_check",
            ),
            nullable=False,
            server_default="proposed",
        ),
        sa.Column(
            "prompt_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompt_versions.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "status_events_pending",
        "status_events",
        ["application_id"],
        postgresql_where=sa.text("state = 'proposed'"),
    )


def downgrade() -> None:
    # Drop in FK-safe order: child tables first
    op.drop_index("status_events_pending", table_name="status_events")
    op.drop_table("status_events")
    op.drop_table("email_messages")
    op.drop_table("email_accounts")
