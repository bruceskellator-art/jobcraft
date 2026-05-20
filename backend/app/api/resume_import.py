from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.user import User
from app.deps import get_current_user, get_llm_client
from app.llm.client import LLMClient
from app.schemas.experience import ExperienceItemRead
from app.schemas.resume_import import ResumeImportResponse
from app.services.resume_extract import extract_text_from_pdf, import_resume_from_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/experience", tags=["experience"])

_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/import", response_model=ResumeImportResponse, status_code=status.HTTP_200_OK)
async def import_resume(
    file: UploadFile,
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> ResumeImportResponse:
    """Upload a PDF resume and extract experience items via LLM.

    Accepts a single PDF file (max 10 MB). Returns the list of created
    ExperienceItems derived from the resume content.
    """
    content_type = (file.content_type or "").lower()
    if content_type not in _PDF_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Only PDF uploads are accepted. Received content-type: '{content_type}'.",
        )

    data = await file.read(_MAX_UPLOAD_BYTES + 1)

    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Empty file.",
        )

    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 10 MB limit.",
        )

    if not data.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File is not a valid PDF.",
        )

    try:
        resume_text = extract_text_from_pdf(data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    created_items = await import_resume_from_text(
        session=session,
        llm=llm,
        user_id=current_user.id,
        resume_text=resume_text,
    )
    await session.commit()

    return ResumeImportResponse(
        created=[ExperienceItemRead.model_validate(item) for item in created_items],
    )
