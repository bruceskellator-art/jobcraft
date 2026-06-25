"""Add scrape_profile to users

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-25

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("scrape_profile", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "scrape_profile")
