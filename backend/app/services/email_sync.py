"""Email sync service — INGEST → MATCH → CLASSIFY → GATE → UPDATE pipeline.

Privacy rules enforced:
- Unmatched messages are NOT persisted (body dropped, only transient).
- Full email bodies are NEVER stored; only metadata + snippet for matched messages.
- OAuth tokens are NEVER logged or returned.
- Per-message failures are isolated (savepoint) and never abort the sync run.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.email_account import EmailAccount
from app.email_sync.classifier import classify_email
from app.email_sync.gate import decide_transition
from app.email_sync.matching import match_message
from app.email_sync.provider import EmailProvider
from app.llm.client import LLMClient
from app.repositories.application import ApplicationRepository
from app.repositories.email import (
    EmailAccountRepository,
    EmailMessageRepository,
    StatusEventRepository,
)

logger = logging.getLogger(__name__)


async def _build_company_domains(
    session: AsyncSession,
    app_ids: list[uuid.UUID],
) -> dict[uuid.UUID, str]:
    """Build a mapping of application_id → company domain from job postings.

    Extracts the domain portion of the company name / URL stored in JobPosting.
    Falls back to an empty string if the domain cannot be determined.
    """
    from sqlalchemy import select

    from app.db.models.application import Application
    from app.db.models.job_posting import JobPosting

    if not app_ids:
        return {}

    result = await session.execute(
        select(Application.id, JobPosting.company)
        .join(JobPosting, Application.job_id == JobPosting.id)
        .where(Application.id.in_(app_ids))
    )
    rows = result.all()

    domains: dict[uuid.UUID, str] = {}
    for app_id, company in rows:
        # Derive a best-effort domain from company name:
        # strip spaces, lowercase, replace spaces with hyphens.
        # In production this would use the job_posting.source_url domain.
        domain = company.lower().replace(" ", "").replace(",", "").replace(".", "")
        domains[app_id] = domain
    return domains


async def _sync_one_message(
    session: AsyncSession,
    llm: LLMClient,
    account: EmailAccount,
    raw: RawEmail,  # type: ignore[name-defined]  # noqa: F821
    open_apps: list[Application],  # type: ignore[name-defined]  # noqa: F821
    company_domains: dict[uuid.UUID, str],
    msg_repo: EmailMessageRepository,
    event_repo: StatusEventRepository,
    app_repo: ApplicationRepository,
) -> dict[str, int]:
    """Process a single message inside an isolated savepoint.

    Returns a dict with keys: matched, applied, proposed.
    Raises nothing — errors are logged and isolated.
    """

    # --- MATCH ---
    app_id, method, confidence = await match_message(
        session,
        llm,
        raw,
        open_apps=open_apps,
        company_domains=company_domains,
    )

    if app_id is None:
        # Privacy rule: unmatched messages are NOT persisted.
        logger.debug(
            "email_sync: no match for message %s — dropped (privacy rule)",
            raw.provider_message_id,
        )
        return {"matched": 0, "applied": 0, "proposed": 0}

    # --- PERSIST metadata + snippet (NEVER full body) ---
    from_domain = raw.from_address.split("@", 1)[1].lower() if "@" in raw.from_address else ""
    msg = await msg_repo.create(
        email_account_id=account.id,
        application_id=app_id,
        provider_message_id=raw.provider_message_id,
        thread_id=raw.thread_id,
        from_address=raw.from_address,
        from_domain=from_domain,
        subject=raw.subject,
        snippet=raw.snippet,
        received_at=raw.received_at,
        match_method=method,
        match_confidence=confidence,
    )

    # --- CLASSIFY ---
    inference = await classify_email(session, llm, raw)

    # --- GATE ---
    # Get current application status for monotonic check
    app = next((a for a in open_apps if a.id == app_id), None)
    current_status = app.status if app is not None else "submitted"
    decision, suggested_status = decide_transition(inference, current_status)

    # --- UPDATE ---
    if decision == "apply":
        await app_repo.update_status(app, suggested_status)  # type: ignore[arg-type]
        await event_repo.create(
            application_id=app_id,
            email_message_id=msg.id,
            from_status=current_status,
            to_status=suggested_status,
            classification=inference.classification,
            confidence=inference.confidence,
            state="applied",
        )
        logger.info(
            "email_sync: auto-applied %s → %s for app %s",
            current_status,
            suggested_status,
            app_id,
        )
        return {"matched": 1, "applied": 1, "proposed": 0}
    else:
        await event_repo.create(
            application_id=app_id,
            email_message_id=msg.id,
            from_status=current_status,
            to_status=suggested_status,
            classification=inference.classification,
            confidence=inference.confidence,
            state="proposed",
        )
        logger.info(
            "email_sync: proposed %s → %s for app %s (confidence=%.2f, requires_human=%s)",
            current_status,
            suggested_status,
            app_id,
            inference.confidence,
            inference.requires_human,
        )
        return {"matched": 1, "applied": 0, "proposed": 1}


async def sync_account(
    session: AsyncSession,
    llm: LLMClient,
    account: EmailAccount,
    provider: EmailProvider,
) -> dict[str, int]:
    """Run a full incremental sync for one email account.

    Pipeline per message:
        INGEST → MATCH → CLASSIFY → GATE → UPDATE

    Privacy rules:
    - Unmatched messages are NOT persisted.
    - Full email body is NEVER stored; only metadata + snippet for matched msgs.
    - Per-message failures are isolated via savepoints; sync continues.

    Returns:
        {ingested, matched, applied, proposed} counts.
    """
    # --- INGEST ---
    raw_messages, new_cursor = await provider.list_since(account.sync_cursor)

    msg_repo = EmailMessageRepository(session)
    event_repo = StatusEventRepository(session)
    app_repo = ApplicationRepository(session)

    # Load open applications for this user
    open_apps = await app_repo.list_by_user(account.user_id)
    open_app_ids = [a.id for a in open_apps]
    company_domains = await _build_company_domains(session, open_app_ids)

    counts = {"ingested": 0, "matched": 0, "applied": 0, "proposed": 0}

    for raw in raw_messages:
        counts["ingested"] += 1

        # Idempotency: skip messages already processed
        existing = await msg_repo.get_by_provider_id(
            account.id, raw.provider_message_id
        )
        if existing is not None:
            logger.debug(
                "email_sync: skipping already-processed message %s",
                raw.provider_message_id,
            )
            continue

        # Isolate each message in a savepoint so per-message errors
        # never abort the entire sync.
        try:
            async with session.begin_nested():
                result = await _sync_one_message(
                    session,
                    llm,
                    account,
                    raw,
                    open_apps,
                    company_domains,
                    msg_repo,
                    event_repo,
                    app_repo,
                )
                counts["matched"] += result["matched"]
                counts["applied"] += result["applied"]
                counts["proposed"] += result["proposed"]
        except Exception:
            logger.exception(
                "email_sync: error processing message %s — isolated, continuing sync",
                raw.provider_message_id,
            )

    # --- Update cursor + last_synced_at ---
    account_repo = EmailAccountRepository(session)
    await account_repo.update_cursor(account, new_cursor)

    logger.info(
        "email_sync: account=%s ingested=%d matched=%d applied=%d proposed=%d",
        account.id,
        counts["ingested"],
        counts["matched"],
        counts["applied"],
        counts["proposed"],
    )
    return counts
