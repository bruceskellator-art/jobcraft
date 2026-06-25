from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.user import User
from app.deps import get_current_user
from app.schemas.scrape_profile import ScrapeProfileConfig
from app.schemas.user_prefs import UiPrefs

router = APIRouter(prefix="/api/settings", tags=["settings"])

_DEFAULTS = ScrapeProfileConfig()
_UI_DEFAULTS = UiPrefs()


@router.get("/scrape-profile", response_model=ScrapeProfileConfig)
async def get_scrape_profile(
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ScrapeProfileConfig:
    """Return the user's saved scrape profile, or defaults if not yet set."""
    if current_user.scrape_profile is None:
        return _DEFAULTS
    return ScrapeProfileConfig.model_validate(current_user.scrape_profile)


@router.put("/scrape-profile", response_model=ScrapeProfileConfig)
async def put_scrape_profile(
    config: ScrapeProfileConfig,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ScrapeProfileConfig:
    """Save the user's scrape profile and return it."""
    current_user.scrape_profile = config.model_dump()
    await session.commit()
    await session.refresh(current_user)
    return config


@router.get("/ui-prefs", response_model=UiPrefs)
async def get_ui_prefs(
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> UiPrefs:
    """Return the user's saved UI preferences, or defaults if not yet set."""
    if current_user.ui_prefs is None:
        return _UI_DEFAULTS
    return UiPrefs.model_validate(current_user.ui_prefs)


@router.put("/ui-prefs", response_model=UiPrefs)
async def put_ui_prefs(
    prefs: UiPrefs,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> UiPrefs:
    """Save the user's UI preferences and return them."""
    current_user.ui_prefs = prefs.model_dump()
    await session.commit()
    await session.refresh(current_user)
    return prefs
