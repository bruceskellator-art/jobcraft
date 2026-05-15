"""Phase 1 tables: users, experience_items, prompt_versions, llm_calls

Revision ID: 0001
Revises:
Create Date: 2026-06-24

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text, unique=True, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "experience_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.Text,
            sa.CheckConstraint(
                "kind IN ('work', 'project', 'education', 'skill', 'achievement')",
                name="experience_items_kind_check",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("organization", sa.Text, nullable=True),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text),
            server_default="{}",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            server_default="{}",
        ),
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
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("template", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("temperature", sa.Float, nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            server_default="{}",
        ),
        sa.Column("is_active", sa.Boolean, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("name", "version", name="uq_prompt_versions_name_version"),
    )

    op.create_index(
        "one_active_per_name",
        "prompt_versions",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.create_table(
        "llm_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "prompt_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompt_versions.id"),
            nullable=False,
        ),
        sa.Column("inputs", postgresql.JSONB, nullable=False),
        sa.Column("rendered_prompt", sa.Text, nullable=False),
        sa.Column("response", sa.Text, nullable=False),
        sa.Column("parsed_response", postgresql.JSONB, nullable=True),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "called_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("llm_calls")
    op.drop_index("one_active_per_name", table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_table("experience_items")
    op.drop_table("users")
