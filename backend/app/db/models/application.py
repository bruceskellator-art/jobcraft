from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_VALID_STATUSES = (
    "interested",
    "queued",
    "auto_filling",
    "needs_review",
    "submitted",
    "blocked",
    "failed",
    "phone_screen",
    "technical",
    "onsite",
    "offer",
    "rejected",
    "withdrawn",
)

_VALID_APPLY_MODES = ("auto", "assisted", "manual")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ("
            "'interested','queued','auto_filling','needs_review','submitted',"
            "'blocked','failed','phone_screen','technical','onsite','offer',"
            "'rejected','withdrawn'"
            ")",
            name="applications_status_check",
        ),
        sa.CheckConstraint(
            "apply_mode IN ('auto','assisted','manual')",
            name="applications_apply_mode_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("job_postings.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    apply_mode: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    apply_confidence: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    resume_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("artifacts.id"), nullable=True
    )
    cover_letter_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("artifacts.id"), nullable=True
    )
    submitted_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
