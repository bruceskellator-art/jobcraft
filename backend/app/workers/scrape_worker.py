"""arq worker for background scrape runs.

The real logic lives in app.services.scrape.execute_scrape_run.
This module is intentionally thin: it builds deps and delegates.

To run the worker (requires Redis):
    arq app.workers.scrape_worker.WorkerSettings

NOTE: This worker requires Redis and is NOT executed in tests.
     It is import-safe; missing Redis or missing arq does not crash imports.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


async def scrape_run_task(ctx: dict, run_id: str) -> dict:
    """arq task: execute a single persisted scrape run by ID.

    The run's request (boards/companies/keywords, filters, extract flag) is read
    from the ScrapeRun row inside execute_scrape_run, so the task only needs the
    run id. Deps are built inside the task to keep the worker stateless.

    Returns a dict with outcome info for arq job-result storage.
    """
    from app.config import get_settings  # noqa: PLC0415
    from app.db.base import make_engine, make_session_factory  # noqa: PLC0415
    from app.deps import get_llm_factory, get_source_factory  # noqa: PLC0415
    from app.services.scrape import execute_scrape_run  # noqa: PLC0415

    settings = get_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)

    try:
        await execute_scrape_run(
            uuid.UUID(run_id),
            session_factory=factory,
            source_factory=get_source_factory(),
            llm_factory=get_llm_factory(),
        )
        return {"outcome": "completed", "run_id": run_id}
    finally:
        await engine.dispose()


class WorkerSettings:
    """arq WorkerSettings for the scrape worker.

    Redis URL is read from app settings at worker startup.
    """

    functions = [scrape_run_task]

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
