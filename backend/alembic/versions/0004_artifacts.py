"""Phase 4 table: artifacts

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-24

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_postings.id"),
            nullable=True,
        ),
        sa.Column(
            "kind",
            sa.Text,
            sa.CheckConstraint(
                "kind IN ('resume', 'cover_letter')", name="artifacts_kind_check"
            ),
            nullable=False,
        ),
        sa.Column(
            "format",
            sa.Text,
            sa.CheckConstraint(
                "format IN ('markdown', 'pdf', 'html')", name="artifacts_format_check"
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("is_baseline", sa.Boolean, server_default=sa.false()),
        sa.Column("scores", postgresql.JSONB, nullable=True),
        sa.Column(
            "prompt_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompt_versions.id"),
            nullable=True,
        ),
        sa.Column("generation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("artifacts")
