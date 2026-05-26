"""Phase 3 table: matches

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-24

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matches",
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
        sa.Column("overall_score", sa.Float, nullable=False),
        sa.Column("dimension_scores", postgresql.JSONB, nullable=False),
        sa.Column("gaps", postgresql.JSONB, nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column(
            "prompt_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompt_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id", "job_id", "prompt_version_id", name="uq_matches_user_job_prompt"
        ),
    )


def downgrade() -> None:
    op.drop_table("matches")
