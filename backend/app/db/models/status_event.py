from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StatusEvent(Base):
    __tablename__ = "status_events"
    __table_args__ = (
        sa.CheckConstraint(
            "state IN ('proposed', 'applied', 'dismissed')",
            name="status_events_state_check",
        ),
        # Non-unique partial index: fast lookup of unresolved proposals per application.
        # Both dialects enforce the same filter so local SQLite tests match Postgres.
        Index(
            "status_events_pending",
            "application_id",
            postgresql_where=text("state = 'proposed'"),
            sqlite_where=text("state = 'proposed'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("applications.id"), nullable=False
    )
    email_message_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("email_messages.id"), nullable=True
    )
    from_status: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    to_status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    classification: Mapped[str] = mapped_column(sa.Text, nullable=False)
    confidence: Mapped[float] = mapped_column(sa.Float, nullable=False)
    state: Mapped[str] = mapped_column(
        sa.Text, nullable=False, server_default="proposed"
    )
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("prompt_versions.id"), nullable=True
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    resolved_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
