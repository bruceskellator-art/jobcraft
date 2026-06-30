from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.admin_calls import router as admin_calls_router
from app.api.admin_evals import router as admin_evals_router
from app.api.admin_prompts import router as admin_prompts_router
from app.api.answers import router as answers_router
from app.api.apply import router as apply_router
from app.api.email import router as email_router
from app.api.experience import router as experience_router
from app.api.generation import router as generation_router
from app.api.jobs import router as jobs_router
from app.api.match import router as match_router
from app.api.profile import router as profile_router
from app.api.resume_import import router as resume_import_router
from app.api.settings import router as settings_router
from app.config import get_settings

logger = logging.getLogger(__name__)


async def _create_arq_pool() -> object | None:
    """Create an arq Redis pool for scrape dispatch, or None if unavailable.

    Returns None when JOBCRAFT_SCRAPE_DISPATCH_MODE != "arq" or Redis cannot be
    reached — callers then fall back to in-process dispatch so local dev (and the
    no-Docker quickstart) keeps working without Redis.
    """
    settings = get_settings()
    if settings.scrape_dispatch_mode != "arq":
        logger.info("scrape_dispatch_mode=%s — arq pool not created", settings.scrape_dispatch_mode)
        return None
    try:
        from arq import create_pool  # noqa: PLC0415
        from arq.connections import RedisSettings  # noqa: PLC0415

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        logger.info("arq Redis pool ready — scrape runs will dispatch to workers")
        return pool
    except Exception as exc:  # noqa: BLE001 - degrade gracefully on any connection error
        logger.warning(
            "Could not connect to Redis for scrape dispatch (%s); "
            "using in-process fallback. Start redis + the scrape worker to enable "
            "background workers: arq app.workers.scrape_worker.WorkerSettings",
            exc,
        )
        return None


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Manage the arq Redis pool lifecycle for scrape dispatch."""
    application.state.arq_pool = await _create_arq_pool()
    try:
        yield
    finally:
        pool = getattr(application.state, "arq_pool", None)
        if pool is not None:
            # arq's ArqRedis (redis>=5) prefers aclose(); fall back for older clients.
            closer = getattr(pool, "aclose", None) or pool.close
            await closer()
            logger.info("arq Redis pool closed")


def _cors_headers(request: Request, settings_origins: list[str]) -> dict[str, str]:
    """Return CORS headers for the request's origin if it is allowed."""
    origin = request.headers.get("origin")
    if origin and origin in settings_origins:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        }
    return {}


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    origins = settings.cors_origins

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=_cors_headers(request, origins),
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers=_cors_headers(request, origins),
        )

    application.include_router(admin_calls_router)
    application.include_router(admin_evals_router)
    application.include_router(admin_prompts_router)
    application.include_router(answers_router)
    application.include_router(apply_router)
    application.include_router(email_router)
    application.include_router(experience_router)
    application.include_router(generation_router)
    application.include_router(jobs_router)
    application.include_router(match_router)
    application.include_router(profile_router)
    application.include_router(resume_import_router)
    application.include_router(settings_router)

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
