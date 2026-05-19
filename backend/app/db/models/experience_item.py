from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_VALID_KINDS = ("work", "project", "education", "skill", "achievement")


class ExperienceItem(Base):
    __tablename__ = "experience_items"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(
        sa.Text,
        sa.CheckConstraint(
            "kind IN ('work', 'project', 'education', 'skill', 'achievement')",
            name="experience_items_kind_check",
        ),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    organization: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    start_date: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    end_date: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()).with_variant(sa.JSON(), "sqlite"),
        default=list,
        server_default="{}",
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB().with_variant(sa.JSON(), "sqlite"),
        server_default="{}",
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
