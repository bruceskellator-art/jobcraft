from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JobPosting(Base):
    __tablename__ = "job_postings"
    __table_args__ = (
        sa.UniqueConstraint("source", "source_id", name="uq_job_postings_source_source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    company: Mapped[str] = mapped_column(sa.Text, nullable=False)
    company_logo_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    location: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    remote_policy: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    raw_content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    extracted: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(sa.JSON(), "sqlite"),
        nullable=True,
    )
    scraped_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
