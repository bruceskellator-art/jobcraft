"""Add sort_order to experience_items

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-25

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "experience_items",
        sa.Column("sort_order", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("experience_items", "sort_order")
