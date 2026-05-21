"""Phase 2 table: job_postings

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-24

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_postings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("source_id", sa.Text, nullable=True),
        sa.Column("company", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("location", sa.Text, nullable=True),
        sa.Column("remote_policy", sa.Text, nullable=True),
        sa.Column("raw_content", sa.Text, nullable=False),
        sa.Column("extracted", postgresql.JSONB, nullable=True),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("source", "source_id", name="uq_job_postings_source_source_id"),
    )


def downgrade() -> None:
    op.drop_table("job_postings")
