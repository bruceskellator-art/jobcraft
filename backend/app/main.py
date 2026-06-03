from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin_evals import router as admin_evals_router
from app.api.answers import router as answers_router
from app.api.experience import router as experience_router
from app.api.generation import router as generation_router
from app.api.jobs import router as jobs_router
from app.api.match import router as match_router
from app.api.profile import router as profile_router
from app.api.resume_import import router as resume_import_router
from app.config import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(admin_evals_router)
    application.include_router(answers_router)
    application.include_router(experience_router)
    application.include_router(generation_router)
    application.include_router(jobs_router)
    application.include_router(match_router)
    application.include_router(profile_router)
    application.include_router(resume_import_router)

    @application.get("/health")
    async def health() -> dict[str, str]:
        """Return application health status."""
        return {"status": "ok", "app": settings.app_name}

    @application.get("/")
    async def root() -> dict[str, str]:
        """Return application metadata."""
        return {"name": settings.app_name, "version": "0.1.0"}

    return application


app = create_app()
