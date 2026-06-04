"""Autopilot configuration service.

RESERVED KEY
------------
AutopilotConfig is persisted as a JSON-encoded ProfileField with the
reserved key "__autopilot__" (is_knockout=False). No user-facing profile
field may use this key. The leading/trailing double underscores signal
that it is a system-managed entry.
"""

from __future__ import annotations

import json
import uuid
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.profile_field import ProfileFieldRepository

_AUTOPILOT_KEY = "__autopilot__"


class AutopilotConfig(BaseModel):
    """Configuration for the autopilot application engine.

    Fields match §4.8 of the JobCraft spec exactly.
    """

    mode: Literal["off", "selective", "full"] = "selective"
    auto_submit_sources: list[str] = Field(
        default_factory=lambda: ["linkedin_easy_apply", "mycareersfuture"]
    )
    min_confidence: float = 0.75
    min_fit: float = 0.55
    daily_cap: int = 80


async def get_autopilot_config(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> AutopilotConfig:
    """Return the persisted AutopilotConfig for user_id.

    Falls back to default values when no config has been saved yet.
    """
    repo = ProfileFieldRepository(session)
    field = await repo.get_by_key(user_id, _AUTOPILOT_KEY)
    if field is None:
        return AutopilotConfig()

    raw = json.loads(field.value)
    return AutopilotConfig.model_validate(raw)


async def set_autopilot_config(
    session: AsyncSession,
    user_id: uuid.UUID,
    cfg: AutopilotConfig,
) -> None:
    """Persist cfg as a JSON ProfileField for user_id.

    Uses the reserved key "__autopilot__" with is_knockout=False.
    The repository handles insert-or-update transparently.
    """
    repo = ProfileFieldRepository(session)
    await repo.upsert(
        user_id=user_id,
        key=_AUTOPILOT_KEY,
        value=cfg.model_dump_json(),
        is_knockout=False,
    )
