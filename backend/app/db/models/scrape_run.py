from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Lifecycle states for a background scrape run.
SCRAPE_STATUSES = ("pending", "running", "succeeded", "failed")


class ScrapeRun(Base):
    """A single background scrape job and its outcome.

    Created in ``pending`` when enqueued, flipped to ``running`` when the
    background task starts, and finalized to ``succeeded``/``failed`` with the
    per-source breakdown stored in ``runs``.
    """

    __tablename__ = "scrape_runs"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="scrape_runs_status_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, default="pending")
    # Snapshot of the ScrapeRequest that triggered this run (for display).
    request: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(sa.JSON(), "sqlite"), nullable=True
    )
    total_created: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    # List of per-source ScrapeRunLogView dicts; null until the run finishes.
    runs: Mapped[list | None] = mapped_column(
        JSONB().with_variant(sa.JSON(), "sqlite"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    started_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
