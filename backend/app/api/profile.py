from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.user import User
from app.deps import get_current_user
from app.repositories.profile_field import ProfileFieldRepository
from app.schemas.apply_profile import (
    AutopilotConfigIO,
    ProfileFieldRead,
    ProfileFieldUpsert,
)
from app.services.autopilot import (
    AutopilotConfig,
    get_autopilot_config,
    set_autopilot_config,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])

_RESERVED_KEYS = {"__autopilot__"}


def _get_repo(session: AsyncSession = Depends(get_session)) -> ProfileFieldRepository:  # noqa: B008
    return ProfileFieldRepository(session)


@router.get("/fields", response_model=list[ProfileFieldRead])
async def list_profile_fields(
    current_user: User = Depends(get_current_user),  # noqa: B008
    repo: ProfileFieldRepository = Depends(_get_repo),  # noqa: B008
) -> list[ProfileFieldRead]:
    """List all profile fields for the current user, excluding reserved system fields."""
    all_fields = await repo.list_by_user(current_user.id)
    return [f for f in all_fields if f.key not in _RESERVED_KEYS]  # type: ignore[misc]


@router.put("/fields", response_model=ProfileFieldRead)
async def upsert_profile_field(
    data: ProfileFieldUpsert,
    current_user: User = Depends(get_current_user),  # noqa: B008
    repo: ProfileFieldRepository = Depends(_get_repo),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ProfileFieldRead:
    """Create or update a profile field by key. Reserved keys are forbidden."""
    if data.key in _RESERVED_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Key '{data.key}' is reserved for system use.",
        )
    field = await repo.upsert(
        user_id=current_user.id,
        key=data.key,
        value=data.value,
        is_knockout=data.is_knockout,
    )
    await session.commit()
    return field  # type: ignore[return-value]


@router.delete("/fields/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile_field(
    key: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    repo: ProfileFieldRepository = Depends(_get_repo),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    """Delete a profile field by key."""
    if key in _RESERVED_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Key '{key}' is reserved for system use.",
        )
    field = await repo.get_by_key(current_user.id, key)
    if field is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile field not found.",
        )
    await repo.delete(field)
    await session.commit()


@router.get("/autopilot", response_model=AutopilotConfigIO)
async def get_autopilot(
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> AutopilotConfigIO:
    """Return the current autopilot configuration, or defaults if unset."""
    cfg = await get_autopilot_config(session, current_user.id)
    return AutopilotConfigIO(**cfg.model_dump())


@router.put("/autopilot", response_model=AutopilotConfigIO)
async def put_autopilot(
    data: AutopilotConfigIO,
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> AutopilotConfigIO:
    """Persist the autopilot configuration for the current user."""
    cfg = AutopilotConfig(**data.model_dump())
    await set_autopilot_config(session, current_user.id, cfg)
    await session.commit()
    return data
