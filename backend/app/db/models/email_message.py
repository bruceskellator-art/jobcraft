from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailMessage(Base):
    __tablename__ = "email_messages"
    __table_args__ = (
        sa.UniqueConstraint(
            "email_account_id",
            "provider_message_id",
            name="uq_email_messages_account_msg",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    email_account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("email_accounts.id"), nullable=False
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("applications.id"), nullable=True
    )
    provider_message_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    thread_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    from_address: Mapped[str] = mapped_column(sa.Text, nullable=False)
    from_domain: Mapped[str] = mapped_column(sa.Text, nullable=False)
    subject: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    received_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    match_method: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
