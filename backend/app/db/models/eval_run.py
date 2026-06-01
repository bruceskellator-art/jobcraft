from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    suite_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("prompt_versions.id"), nullable=False
    )
    results: Mapped[list] = mapped_column(
        JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False
    )
    aggregate_scores: Mapped[dict] = mapped_column(
        JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False
    )
    started_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
