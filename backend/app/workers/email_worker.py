"""arq worker for email sync background tasks.

The real pipeline logic lives in app.services.email_sync.
This module is intentionally thin: it builds deps inside the task and delegates.

NOTE: This worker requires Redis and is NOT executed in tests.
     It is import-safe; missing Redis or missing arq does not crash imports.

Cron schedule:
    sync_all_accounts_cron runs every 15 minutes (900 seconds).
    Configure by setting JOBCRAFT_REDIS_URL and running:
        arq app.workers.email_worker.WorkerSettings
"""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


async def sync_email_account_task(ctx: dict, account_id: str) -> dict:
    """arq task: run an incremental email sync for one EmailAccount by ID.

    ctx is provided by arq and contains any state from WorkerSettings.on_startup.
    Deps are built inside the task to keep the worker stateless between runs.

    Returns a dict with counts for arq job-result storage.
    """
    from app.config import get_settings  # noqa: PLC0415
    from app.db.base import make_engine, make_session_factory  # noqa: PLC0415
    from app.email_sync.crypto import TokenCrypto  # noqa: PLC0415
    from app.email_sync.provider import (  # noqa: PLC0415
        EmailProvider,
        GmailProvider,
        OutlookProvider,
    )
    from app.llm.adapters.anthropic import AnthropicAdapter  # noqa: PLC0415
    from app.llm.client import LLMClient  # noqa: PLC0415
    from app.repositories.email import EmailAccountRepository  # noqa: PLC0415
    from app.services.email_sync import sync_account  # noqa: PLC0415

    settings = get_settings()

    key = settings.token_encryption_key
    if not key:
        logger.warning(
            "email_worker: token_encryption_key not set — skipping account_id=%s",
            account_id,
        )
        return {"outcome": "skipped", "reason": "email_sync_not_configured"}

    crypto = TokenCrypto(key)
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)

    try:
        async with factory() as session:
            repo = EmailAccountRepository(session)
            account = await repo.get(uuid.UUID(account_id))
            if account is None:
                logger.warning(
                    "email_worker: account_id=%s not found; skipping", account_id
                )
                return {"outcome": "not_found", "account_id": account_id}

            # Decrypt token to build provider — never log the token
            try:
                token = crypto.decrypt(account.oauth_token_enc)
            except Exception:
                logger.exception(
                    "email_worker: token decryption failed for account_id=%s", account_id
                )
                return {"outcome": "error", "reason": "token_decryption_failed"}

            access_token: str = token.get("access_token", "")
            provider: EmailProvider
            if account.provider == "gmail":
                provider = GmailProvider(access_token=access_token)
            elif account.provider == "outlook":
                provider = OutlookProvider(access_token=access_token)
            else:
                logger.error(
                    "email_worker: unknown provider %r for account_id=%s",
                    account.provider,
                    account_id,
                )
                return {"outcome": "error", "reason": "unknown_provider"}

            llm = LLMClient(session=session, adapter=AnthropicAdapter())
            counts = await sync_account(session, llm, account, provider)
            await session.commit()

        logger.info(
            "email_worker: account_id=%s counts=%s", account_id, counts
        )
        return {"outcome": "ok", "account_id": account_id, **counts}
    finally:
        await engine.dispose()


async def sync_all_accounts_cron(ctx: dict) -> None:
    """Periodic cron task: enqueue a sync job for every active email account.

    Runs every 15 minutes as defined in WorkerSettings.cron_jobs.
    Enqueues one sync_email_account_task per active account so each account's
    sync is isolated and failures don't block other accounts.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from app.config import get_settings  # noqa: PLC0415
    from app.db.base import make_engine, make_session_factory  # noqa: PLC0415
    from app.db.models.email_account import EmailAccount  # noqa: PLC0415

    settings = get_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)

    try:
        async with factory() as session:
            result = await session.execute(
                select(EmailAccount).where(EmailAccount.status == "active")
            )
            accounts = list(result.scalars().all())

        # Enqueue via arq — use the pool from ctx if available, else skip
        pool = ctx.get("redis")
        if pool is None:
            logger.warning("email_worker: no redis pool in ctx — skipping cron enqueue")
            return

        for account in accounts:
            await pool.enqueue_job(
                "sync_email_account_task", str(account.id)
            )
            logger.debug("email_worker: enqueued sync for account_id=%s", account.id)

        logger.info("email_worker: cron enqueued %d account(s)", len(accounts))
    finally:
        await engine.dispose()


class WorkerSettings:
    """arq WorkerSettings for the email sync worker.

    Redis URL is read from app settings at worker startup.

    Cron schedule: every 15 minutes (900 seconds).
    To start the worker:
        arq app.workers.email_worker.WorkerSettings
    """

    functions = [sync_email_account_task]

    # Periodic 15-minute poll for all active accounts.
    # Uses arq's cron helper; imported lazily to keep this module import-safe.
    @classmethod
    def _build_cron_jobs(cls) -> list:
        try:
            from arq.cron import cron  # noqa: PLC0415

            return [cron(sync_all_accounts_cron, minute={0, 15, 30, 45})]
        except ImportError:
            logger.warning("email_worker: arq not available — cron jobs not registered")
            return []

    cron_jobs = _build_cron_jobs.__func__(None)  # type: ignore[attr-defined]

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
