"""arq worker for apply pipeline background tasks.

The real logic lives in app.services.apply_orchestration.
This module is intentionally thin: it builds deps and delegates.

NOTE: This worker requires Redis and is NOT executed in tests.
     It is import-safe; missing Redis or missing arq does not crash imports.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


async def process_application_task(ctx: dict, application_id: str) -> dict:
    """arq task: process a single queued application by ID.

    ctx is provided by arq and contains any state stored in WorkerSettings.on_startup.
    Deps are built inside the task to keep the worker stateless between runs.

    Returns a dict with outcome info for arq job-result storage.
    """
    from app.apply.browser import PlaywrightFormSource
    from app.apply.strategies import ApplyStrategy, GenericFormStrategy, GreenhouseFormStrategy
    from app.config import get_settings  # noqa: PLC0415
    from app.db.base import make_engine, make_session_factory
    from app.embeddings.openai_adapter import OpenAIEmbeddingAdapter
    from app.llm.adapters.anthropic import AnthropicAdapter
    from app.llm.client import LLMClient
    from app.repositories.application import ApplicationRepository
    from app.services.apply_orchestration import process_application
    from app.services.autopilot import get_autopilot_config
    from app.vectorstore.qdrant_adapter import QdrantVectorStore

    settings = get_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)

    try:
        async with factory() as session:
            app_repo = ApplicationRepository(session)
            app = await app_repo.get(uuid.UUID(application_id))
            if app is None:
                logger.warning("application_id=%s not found; skipping", application_id)
                return {"outcome": "not_found", "application_id": application_id}

            embed = OpenAIEmbeddingAdapter()
            store = QdrantVectorStore(url=settings.qdrant_url)
            form_source = PlaywrightFormSource()
            strategies: list[ApplyStrategy] = [
                GreenhouseFormStrategy(form_source),
                GenericFormStrategy(form_source),
            ]
            autopilot = await get_autopilot_config(session, app.user_id)

            # Defense-in-depth: never submit when autopilot is off,
            # even if enqueued by another code path.
            if autopilot.mode == "off":
                logger.info(
                    "Autopilot mode='off' for user %s — skipping application %s",
                    app.user_id,
                    application_id,
                )
                return {"outcome": "skipped", "application_id": application_id}

            async with session.begin():
                llm = LLMClient(session=session, adapter=AnthropicAdapter())
                attempt = await process_application(
                    session,
                    llm,
                    embed,
                    store,
                    app.user_id,
                    app,
                    strategies=strategies,
                    form_source=form_source,
                    autopilot=autopilot,
                    dry_run=False,
                )
                await session.commit()

            return {
                "outcome": attempt.outcome,
                "application_id": application_id,
                "attempt_id": str(attempt.id),
            }
    finally:
        await engine.dispose()


class WorkerSettings:
    """arq WorkerSettings for the apply pipeline worker.

    Redis URL is read from app settings at worker startup.
    """

    functions = [process_application_task]

    @staticmethod
    def redis_settings() -> object:
        """Return arq RedisSettings built from app config."""
        try:
            import arq.connections  # noqa: PLC0415

            from app.config import get_settings  # noqa: PLC0415

            url = get_settings().redis_url
            return arq.connections.RedisSettings.from_dsn(url)
        except Exception:
            logger.warning("Could not build RedisSettings; worker will not start.")
            return None
