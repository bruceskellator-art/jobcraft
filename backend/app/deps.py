from __future__ import annotations

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.user import User

# Phase-1 stand-in for real authentication.
# Returns (or creates) a single fixed developer user so that all routes
# have a current_user without a real auth system in place.
# Replace this dependency with a JWT/session resolver once auth is built.
_DEV_EMAIL = "dev@jobcraft.local"
_DEV_NAME = "Dev User"


async def get_current_user(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> User:
    """Return the dev user, creating it on first call.

    Phase-1 auth stub — not suitable for production.
    """
    result = await session.execute(select(User).where(User.email == _DEV_EMAIL))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=_DEV_EMAIL, name=_DEV_NAME)
        session.add(user)
        await session.flush()
        await session.refresh(user)
    return user
