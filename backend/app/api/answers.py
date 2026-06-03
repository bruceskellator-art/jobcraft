from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.user import User
from app.deps import get_current_user, get_embedding_client, get_vector_store
from app.embeddings.base import EmbeddingClient
from app.repositories.answer_bank import AnswerBankRepository
from app.schemas.apply_profile import (
    AnswerBankApprove,
    AnswerBankCreate,
    AnswerBankRead,
)
from app.services.answer_bank_match import find_similar_answer, index_approved_answer
from app.vectorstore.base import VectorStore

router = APIRouter(prefix="/api/answers", tags=["answers"])


def _get_repo(session: AsyncSession = Depends(get_session)) -> AnswerBankRepository:  # noqa: B008
    return AnswerBankRepository(session)


@router.get("", response_model=list[AnswerBankRead])
async def list_answers(
    current_user: User = Depends(get_current_user),  # noqa: B008
    repo: AnswerBankRepository = Depends(_get_repo),  # noqa: B008
) -> list[AnswerBankRead]:
    """List all answer bank entries for the current user."""
    return await repo.list_by_user(current_user.id)  # type: ignore[return-value]


@router.post("", response_model=AnswerBankRead, status_code=status.HTTP_201_CREATED)
async def create_answer(
    data: AnswerBankCreate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    repo: AnswerBankRepository = Depends(_get_repo),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> AnswerBankRead:
    """Create a new answer bank entry as a draft (unapproved)."""
    entry = await repo.create(
        user_id=current_user.id,
        question=data.question,
        answer=data.answer,
        approved=False,
    )
    await session.commit()
    return entry  # type: ignore[return-value]


@router.post("/{answer_id}/approve", response_model=AnswerBankRead)
async def approve_answer(
    answer_id: uuid.UUID,
    data: AnswerBankApprove,
    current_user: User = Depends(get_current_user),  # noqa: B008
    repo: AnswerBankRepository = Depends(_get_repo),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    embed: EmbeddingClient = Depends(get_embedding_client),  # noqa: B008
    store: VectorStore = Depends(get_vector_store),  # noqa: B008
) -> AnswerBankRead:
    """Set the approved flag on an answer bank entry.

    When approved=True, the answer is immediately indexed into the vector store
    so it can be found by /suggest. When approved=False, it is removed from
    future suggestions (the vector store entry remains but the live DB check
    in find_similar_answer will reject it).
    """
    answer = await repo.get(answer_id)
    if answer is None or answer.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Answer not found.",
        )

    updated = await repo.set_approved(answer, data.approved)
    await session.commit()

    if data.approved:
        await index_approved_answer(embed, store, updated)

    return updated  # type: ignore[return-value]


@router.get("/suggest", response_model=AnswerBankRead | None)
async def suggest_answer(
    question: str = Query(min_length=1),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    embed: EmbeddingClient = Depends(get_embedding_client),  # noqa: B008
    store: VectorStore = Depends(get_vector_store),  # noqa: B008
) -> AnswerBankRead | None:
    """Return the best approved answer for a similar question, or null.

    Only approved answers are surfaced. The approved-only safety rule is
    enforced by find_similar_answer which re-checks the live DB row.
    """
    return await find_similar_answer(  # type: ignore[return-value]
        session=session,
        embed=embed,
        store=store,
        user_id=current_user.id,
        question=question,
    )
