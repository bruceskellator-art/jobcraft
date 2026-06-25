"""Generation API endpoints.

Routes
------
POST /api/jobs/{job_id}/generate        Generate a resume or cover letter.
GET  /api/jobs/{job_id}/artifacts       List all artifacts for a job.
GET  /api/artifacts                     List all artifacts for the current user.
GET  /api/artifacts/{artifact_id}       Retrieve a single artifact.
GET  /api/artifacts/{artifact_id}/preview   Render resume HTML (for iframe preview).
GET  /api/artifacts/{artifact_id}/pdf   Render resume to PDF and stream download.
POST /api/artifacts/baseline            Upload a baseline PDF resume and score it.
GET  /api/templates                     List all available resume templates.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.user import User
from app.deps import (
    get_current_user,
    get_llm_client,
)
from app.generator.types import ResumeData, StyleConfig
from app.llm.client import LLMClient
from app.repositories.artifact import ArtifactRepository
from app.repositories.job import JobRepository
from app.resume_templates.registry import TemplateInfo, list_templates
from app.resume_templates.renderer import render_to_html, render_to_pdf
from app.schemas.artifact import ArtifactRead, GenerateRequest
from app.services.generation import generate_for_job, score_baseline
from app.services.resume_extract import extract_text_from_pdf

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generation"])

_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post(
    "/api/jobs/{job_id}/generate",
    response_model=ArtifactRead,
    status_code=status.HTTP_201_CREATED,
)
async def generate_artifact(
    job_id: uuid.UUID,
    body: GenerateRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> ArtifactRead:
    job_repo = JobRepository(session)
    job = await job_repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job posting not found.")

    style = StyleConfig(
        tone=body.style.tone,
        length=body.style.length,
        emphasis=list(body.style.emphasis),
    )

    artifact = await generate_for_job(
        session=session,
        llm=llm,
        user_id=current_user.id,
        job=job,
        kind=body.kind,
        style=style,
        template_id=body.template_id,
    )
    await session.commit()
    await session.refresh(artifact)
    return ArtifactRead.model_validate(artifact)


@router.get("/api/jobs/{job_id}/artifacts", response_model=list[ArtifactRead])
async def list_job_artifacts(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> list[ArtifactRead]:
    repo = ArtifactRepository(session)
    artifacts = await repo.list_for_job(user_id=current_user.id, job_id=job_id)
    return [ArtifactRead.model_validate(a) for a in artifacts]


@router.get("/api/artifacts", response_model=list[ArtifactRead])
async def list_user_artifacts(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> list[ArtifactRead]:
    repo = ArtifactRepository(session)
    artifacts = await repo.list_by_user(user_id=current_user.id)
    return [ArtifactRead.model_validate(a) for a in artifacts]


@router.get("/api/artifacts/{artifact_id}", response_model=ArtifactRead)
async def get_artifact(
    artifact_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ArtifactRead:
    repo = ArtifactRepository(session)
    artifact = await repo.get(artifact_id)
    if artifact is None or artifact.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    return ArtifactRead.model_validate(artifact)


@router.get("/api/artifacts/{artifact_id}/preview", response_class=HTMLResponse)
async def preview_artifact(
    artifact_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> HTMLResponse:
    """Render a resume artifact to HTML for iframe preview.

    Only works for resume artifacts with format='json'. Cover letters
    return their Markdown wrapped in minimal HTML.
    """
    repo = ArtifactRepository(session)
    artifact = await repo.get(artifact_id)
    if artifact is None or artifact.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")

    if artifact.format == "json" and artifact.template_id:
        try:
            data = ResumeData.model_validate_json(artifact.content)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Could not parse resume data: {exc}",
            ) from exc
        html = render_to_html(artifact.template_id, data)
        return HTMLResponse(content=html)

    # Cover letter / markdown fallback
    import html as html_mod
    escaped = html_mod.escape(artifact.content)
    simple_html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>body{font-family:Georgia,serif;font-size:11pt;line-height:1.6;"
        "max-width:700px;margin:2cm auto;color:#222;}p{margin-bottom:0.8em;}</style>"
        "</head><body>"
        + "".join(
            f"<p>{html_mod.escape(line)}</p>" if line.strip() else "<br>"
            for line in artifact.content.splitlines()
        )
        + "</body></html>"
    )
    return HTMLResponse(content=simple_html)


@router.get("/api/artifacts/{artifact_id}/pdf")
async def download_artifact_pdf(
    artifact_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> Response:
    """Render a resume artifact to PDF and stream it as a file download."""
    repo = ArtifactRepository(session)
    artifact = await repo.get(artifact_id)
    if artifact is None or artifact.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")

    if artifact.format != "json" or not artifact.template_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PDF export is only available for template-based resume artifacts.",
        )

    try:
        data = ResumeData.model_validate_json(artifact.content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse resume data: {exc}",
        ) from exc

    try:
        pdf_bytes = render_to_pdf(artifact.template_id, data)
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF render failed: {exc}",
        ) from exc

    safe_name = data.name.replace(" ", "_") if data.name else "resume"
    filename = f"{safe_name}_{artifact.template_id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/api/artifacts/baseline",
    response_model=ArtifactRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_baseline(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> ArtifactRead:
    """Upload a PDF resume as the user's baseline artifact."""
    content_type = (file.content_type or "").lower()
    if content_type not in _PDF_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Only PDF uploads are accepted. Received: '{content_type}'.",
        )

    data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) == 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty file.")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 10 MB.")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="File is not a valid PDF.")

    try:
        resume_text = extract_text_from_pdf(data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    scores = await score_baseline(session=session, llm=llm, user_id=current_user.id, baseline_markdown=resume_text)

    repo = ArtifactRepository(session)
    existing = await repo.get_baseline(user_id=current_user.id)
    if existing is not None:
        await session.delete(existing)
        await session.flush()

    artifact = await repo.create(
        user_id=current_user.id,
        job_id=None,
        kind="resume",
        format="markdown",
        content=resume_text,
        is_baseline=True,
        scores=scores.model_dump(),
    )
    await session.commit()
    await session.refresh(artifact)
    return ArtifactRead.model_validate(artifact)


@router.get("/api/templates", response_model=list[TemplateInfo])
async def list_resume_templates() -> list[TemplateInfo]:
    """List all available resume templates with metadata and thumbnail URLs."""
    return list_templates()
