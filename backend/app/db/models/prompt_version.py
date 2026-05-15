from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompt_versions_name_version"),
        # Only one active version per prompt name. Partial unique index on both
        # dialects so local SQLite tests enforce the same invariant as Postgres
        # without blocking multiple inactive versions of the same name.
        Index(
            "one_active_per_name",
            "name",
            unique=True,
            postgresql_where=text("is_active = TRUE"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    template: Mapped[str] = mapped_column(sa.Text, nullable=False)
    model: Mapped[str] = mapped_column(sa.Text, nullable=False)
    temperature: Mapped[float] = mapped_column(sa.Float, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB().with_variant(sa.JSON(), "sqlite"),
        server_default="{}",
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
