from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import get_session
from app.db.models.user import User
from app.llm.adapters.anthropic import AnthropicAdapter
from app.llm.client import LLMClient

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
    Raises HTTP 501 if called outside the development environment.
    """
    if get_settings().environment != "development":
        raise HTTPException(status_code=501, detail="Auth not configured")

    result = await session.execute(select(User).where(User.email == _DEV_EMAIL))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=_DEV_EMAIL, name=_DEV_NAME)
        session.add(user)
        await session.flush()
        await session.commit()
        await session.refresh(user)
    return user


def get_llm_client(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> LLMClient:
    """Build an LLMClient backed by AnthropicAdapter for production use.

    In tests, override this dependency with a MockAdapter-backed LLMClient:

        app.dependency_overrides[get_llm_client] = lambda: LLMClient(session, MockAdapter(...))
    """
    return LLMClient(session=session, adapter=AnthropicAdapter())
