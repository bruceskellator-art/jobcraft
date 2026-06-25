"""Add ui_prefs to users and company_logo_url to job_postings

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-25

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ui_prefs", sa.JSON(), nullable=True))
    op.add_column(
        "job_postings",
        sa.Column("company_logo_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_postings", "company_logo_url")
    op.drop_column("users", "ui_prefs")
