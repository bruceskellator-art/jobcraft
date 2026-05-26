from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        sa.UniqueConstraint(
            "user_id",
            "job_id",
            "prompt_version_id",
            name="uq_matches_user_job_prompt",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("job_postings.id"), nullable=False
    )
    overall_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    dimension_scores: Mapped[dict] = mapped_column(
        JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False
    )
    gaps: Mapped[list] = mapped_column(
        JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False
    )
    rationale: Mapped[str] = mapped_column(sa.Text, nullable=False)
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("prompt_versions.id"), nullable=False
    )
    computed_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
