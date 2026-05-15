from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("prompt_versions.id"), nullable=False
    )
    inputs: Mapped[dict] = mapped_column(
        JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False
    )
    rendered_prompt: Mapped[str] = mapped_column(sa.Text, nullable=False)
    response: Mapped[str] = mapped_column(sa.Text, nullable=False)
    parsed_response: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(sa.JSON(), "sqlite"), nullable=True
    )
    model: Mapped[str] = mapped_column(sa.Text, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    cost_usd: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(10, 6), nullable=True
    )
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    called_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
