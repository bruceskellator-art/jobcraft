"""Admin endpoints for browsing prompt versions.

Routes
------
GET  /api/admin/prompts           All prompt versions grouped by name.
GET  /api/admin/prompts/{id}      Full detail for a single PromptVersion.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.repositories.prompt_version import PromptVersionRepository
from app.schemas.observability import PromptDetail, PromptVersionRead

router = APIRouter(prefix="/api/admin/prompts", tags=["admin"])


@router.get("", response_model=dict[str, list[PromptVersionRead]])
async def list_prompts_grouped(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, list[PromptVersionRead]]:
    """Return all prompt versions grouped by name, newest version first."""
    repo = PromptVersionRepository(session)
    grouped = await repo.list_grouped()
    return {
        name: [PromptVersionRead.model_validate(pv) for pv in versions]
        for name, versions in grouped.items()
    }


@router.get("/{prompt_id}", response_model=PromptDetail)
async def get_prompt_detail(
    prompt_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> PromptDetail:
    """Return full detail for a single PromptVersion including template."""
    repo = PromptVersionRepository(session)
    pv = await repo.get(prompt_id)
    if pv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PromptVersion not found",
        )
    return PromptDetail.model_validate(pv)
