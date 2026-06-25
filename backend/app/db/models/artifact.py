from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id"), nullable=False
    )
    # NULL for the uploaded baseline résumé.
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("job_postings.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(
        sa.Text,
        sa.CheckConstraint(
            "kind IN ('resume', 'cover_letter')", name="artifacts_kind_check"
        ),
        nullable=False,
    )
    format: Mapped[str] = mapped_column(
        sa.Text,
        sa.CheckConstraint(
            "format IN ('markdown', 'pdf', 'html', 'json')", name="artifacts_format_check"
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # Which HTML/CSS template was used for resume generation. NULL for cover
    # letters and baseline uploads.
    template_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_baseline: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    scores: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(sa.JSON(), "sqlite"), nullable=True
    )
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("prompt_versions.id"), nullable=True
    )
    generation_run_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
