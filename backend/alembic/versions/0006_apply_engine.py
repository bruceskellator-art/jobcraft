"""Phase 6 tables: applications, profile_fields, answer_bank, application_attempts

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-24

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "applications",
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
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text,
            sa.CheckConstraint(
                "status IN ("
                "'interested','queued','auto_filling','needs_review','submitted',"
                "'blocked','failed','phone_screen','technical','onsite','offer',"
                "'rejected','withdrawn'"
                ")",
                name="applications_status_check",
            ),
            nullable=False,
        ),
        sa.Column(
            "apply_mode",
            sa.Text,
            sa.CheckConstraint(
                "apply_mode IN ('auto','assisted','manual')",
                name="applications_apply_mode_check",
            ),
            nullable=True,
        ),
        sa.Column("apply_confidence", sa.Float, nullable=True),
        sa.Column("blocked_reason", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "resume_artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id"),
            nullable=True,
        ),
        sa.Column(
            "cover_letter_artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id"),
            nullable=True,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "profile_fields",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("is_knockout", sa.Boolean, server_default=sa.false()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "key", name="uq_profile_fields_user_key"),
    )

    op.create_table(
        "answer_bank",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("approved", sa.Boolean, server_default=sa.false()),
        sa.Column("reuse_count", sa.Integer, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "application_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id"),
            nullable=False,
        ),
        sa.Column("strategy", sa.Text, nullable=False),
        sa.Column("field_map", postgresql.JSONB, nullable=False),
        sa.Column("overall_confidence", sa.Float, nullable=False),
        sa.Column(
            "outcome",
            sa.Text,
            sa.CheckConstraint(
                "outcome IN ('submitted','queued','blocked','failed')",
                name="application_attempts_outcome_check",
            ),
            nullable=False,
        ),
        sa.Column("blocked_reason", sa.Text, nullable=True),
        sa.Column("screenshot_path", sa.Text, nullable=True),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    # Drop in FK-safe order: child tables first
    op.drop_table("application_attempts")
    op.drop_table("answer_bank")
    op.drop_table("profile_fields")
    op.drop_table("applications")
