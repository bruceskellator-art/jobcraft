from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.user import User
from app.deps import get_current_user
from app.repositories.experience import ExperienceRepository
from app.schemas.experience import (
    ExperienceItemCreate,
    ExperienceItemRead,
    ExperienceItemUpdate,
    ReorderRequest,
)

router = APIRouter(prefix="/api/experience", tags=["experience"])


def _get_repo(session: AsyncSession = Depends(get_session)) -> ExperienceRepository:  # noqa: B008
    return ExperienceRepository(session)


@router.get("", response_model=list[ExperienceItemRead])
async def list_experience_items(
    current_user: User = Depends(get_current_user),  # noqa: B008
    repo: ExperienceRepository = Depends(_get_repo),  # noqa: B008
) -> list[ExperienceItemRead]:
    """List all experience items for the current user."""
    items = await repo.list_by_user(current_user.id)
    return items  # type: ignore[return-value]


@router.post("", response_model=ExperienceItemRead, status_code=status.HTTP_201_CREATED)
async def create_experience_item(
    data: ExperienceItemCreate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    repo: ExperienceRepository = Depends(_get_repo),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ExperienceItemRead:
    """Create a new experience item for the current user."""
    item = await repo.create(current_user.id, data)
    await session.commit()
    return item  # type: ignore[return-value]


@router.get("/{item_id}", response_model=ExperienceItemRead)
async def get_experience_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),  # noqa: B008
    repo: ExperienceRepository = Depends(_get_repo),  # noqa: B008
) -> ExperienceItemRead:
    """Get a single experience item by ID."""
    item = await repo.get(item_id)
    if item is None or item.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item  # type: ignore[return-value]


@router.patch("/{item_id}", response_model=ExperienceItemRead)
async def update_experience_item(
    item_id: uuid.UUID,
    data: ExperienceItemUpdate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    repo: ExperienceRepository = Depends(_get_repo),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ExperienceItemRead:
    """Update fields on an existing experience item."""
    item = await repo.get(item_id)
    if item is None or item.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    updated = await repo.update(item, data)
    await session.commit()
    return updated  # type: ignore[return-value]


@router.put("/reorder", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_experience_items(
    data: ReorderRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    repo: ExperienceRepository = Depends(_get_repo),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    """Update sort_order for all items of a given kind."""
    await repo.reorder_kind(current_user.id, data.kind, data.ids)
    await session.commit()


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_experience_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),  # noqa: B008
    repo: ExperienceRepository = Depends(_get_repo),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    """Delete an experience item."""
    item = await repo.get(item_id)
    if item is None or item.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    await repo.delete(item)
    await session.commit()
