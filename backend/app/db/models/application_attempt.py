from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApplicationAttempt(Base):
    __tablename__ = "application_attempts"
    __table_args__ = (
        sa.CheckConstraint(
            "outcome IN ('submitted','queued','blocked','failed')",
            name="application_attempts_outcome_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("applications.id"), nullable=False
    )
    strategy: Mapped[str] = mapped_column(sa.Text, nullable=False)
    field_map: Mapped[list] = mapped_column(
        JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False
    )
    overall_confidence: Mapped[float] = mapped_column(sa.Float, nullable=False)
    outcome: Mapped[str] = mapped_column(sa.Text, nullable=False)
    blocked_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    attempted_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
