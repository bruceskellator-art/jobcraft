"""Email-to-application matching: cheap deterministic → LLM tie-break.

Strategy (cheapest first):
1. thread_id match  — continues a known application thread (exact, free)
2. from_domain match — sender domain == application's company domain (free)
3. ATS sender domain — known ATS (greenhouse.io, etc.) + single open app (free)
4. LLM tie-break — ONLY when ambiguous (multiple open apps at one company)

Unmatched → (None, None, 0.0).

LLM is NEVER called for deterministic cases. This is the same two-stage cost
discipline as the Matcher (§4.3).
"""
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.email_sync.provider import RawEmail

if TYPE_CHECKING:
    from app.db.models.application import Application
    from app.llm.client import LLMClient

logger = logging.getLogger(__name__)

# Well-known ATS sender domains — emails FROM these senders are almost certainly
# job-application related. Extend as new ATS systems are encountered.
ATS_SENDER_DOMAINS: frozenset[str] = frozenset(
    {
        "greenhouse.io",
        "lever.co",
        "ashbyhq.com",
        "myworkday.com",
        "myworkdayjobs.com",
        "icims.com",
        "jobvite.com",
        "smartrecruiters.com",
        "workable.com",
        "breezy.hr",
        "recruiterbox.com",
        "bamboohr.com",
        "taleo.net",
        "successfactors.com",
        "ultipro.com",
        "kronos.com",
        "rippling.com",
        "dover.com",
    }
)

_LLM_PROMPT_NAME = "match_email_to_application"
_LLM_PROMPT_VERSION = 1
_LLM_PROMPT_MODEL = "claude-haiku-4-5"
_LLM_PROMPT_TEMPERATURE = 0.0
_LLM_PROMPT_TEMPLATE = """\
You are matching a recruitment email to an open job application.

Open applications (JSON array):
{{ applications_json }}

Email metadata:
From: {{ from_address }}
Subject: {{ subject }}
Snippet: {{ snippet }}

If the email clearly belongs to exactly one application, return that application's
UUID as a JSON string. If you cannot determine a match, return null.
Return ONLY the JSON value — no prose, no fences:
"""

_METHOD_THREAD = "thread"
_METHOD_DOMAIN = "domain"
_METHOD_ATS = "ats_sender"
_METHOD_LLM = "llm"

_CONFIDENCE_THREAD = 1.0
_CONFIDENCE_DOMAIN = 0.85
_CONFIDENCE_ATS = 0.80
_CONFIDENCE_LLM_MATCH = 0.70


def _extract_domain(address: str) -> str:
    """Extract the domain part from an email address."""
    if "@" in address:
        return address.split("@", 1)[1].lower().strip()
    return address.lower().strip()


async def _ensure_llm_match_prompt(session: AsyncSession) -> PromptVersion:  # type: ignore[name-defined]  # noqa: F821
    """Return or create the LLM email-match prompt version (savepoint pattern)."""
    from sqlalchemy.exc import IntegrityError

    from app.db.models.prompt_version import PromptVersion

    result = await session.execute(
        select(PromptVersion).where(
            PromptVersion.name == _LLM_PROMPT_NAME,
            PromptVersion.is_active == True,  # noqa: E712
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    prompt = PromptVersion(
        name=_LLM_PROMPT_NAME,
        version=_LLM_PROMPT_VERSION,
        template=_LLM_PROMPT_TEMPLATE,
        model=_LLM_PROMPT_MODEL,
        temperature=_LLM_PROMPT_TEMPERATURE,
        is_active=True,
    )
    try:
        async with session.begin_nested():
            session.add(prompt)
            await session.flush()
            await session.refresh(prompt)
    except IntegrityError:
        result = await session.execute(
            select(PromptVersion).where(
                PromptVersion.name == _LLM_PROMPT_NAME,
                PromptVersion.is_active == True,  # noqa: E712
            )
        )
        prompt = result.scalar_one()
    return prompt


async def _llm_tie_break(
    session: AsyncSession,
    llm: LLMClient,
    raw: RawEmail,
    candidates: list[Application],
) -> uuid.UUID | None:
    """Ask the LLM to pick one application from *candidates*.

    Returns the matched application UUID or None if LLM cannot determine.
    Only called when multiple candidates share the same domain.
    """
    import json

    apps_json = json.dumps(
        [
            {"id": str(app.id), "status": app.status}
            for app in candidates
        ]
    )
    prompt = await _ensure_llm_match_prompt(session)
    from app.llm.response import LLMResponse  # noqa: F401

    response: LLMResponse[None] = await llm.complete(
        prompt.id,
        inputs={
            "applications_json": apps_json,
            "from_address": raw.from_address,
            "subject": raw.subject or "",
            "snippet": raw.snippet or "",
        },
    )
    raw_text = (response.raw or "").strip()
    if not raw_text or raw_text.lower() in ("null", "none", '""', ""):
        return None
    try:
        # Strip surrounding quotes if present
        candidate_id_str = raw_text.strip('"')
        return uuid.UUID(candidate_id_str)
    except (ValueError, AttributeError):
        logger.warning("LLM tie-break returned non-UUID: %r", raw_text)
        return None


async def match_message(
    session: AsyncSession,
    llm: LLMClient,
    raw: RawEmail,
    *,
    open_apps: list[Application],
    company_domains: dict[uuid.UUID, str],
) -> tuple[uuid.UUID | None, str | None, float]:
    """Match a RawEmail to an open Application.

    Args:
        session: SQLAlchemy async session.
        llm: LLMClient — only invoked for LLM tie-break.
        raw: The email to match.
        open_apps: List of open Application records for the user.
        company_domains: Mapping of application_id → company domain string.
            Callers extract company domain from the related JobPosting.

    Returns:
        (application_id, method, confidence) where application_id is None
        when no match is found.
    """
    from_domain = _extract_domain(raw.from_address)

    # --- Stage 1: thread_id continues a known application thread ---
    if raw.thread_id:
        from app.db.models.email_message import EmailMessage

        result = await session.execute(
            select(EmailMessage).where(
                EmailMessage.thread_id == raw.thread_id,
                EmailMessage.application_id.isnot(None),
            )
        )
        existing_msg = result.scalars().first()
        if existing_msg is not None and existing_msg.application_id is not None:
            logger.debug(
                "match_message: thread match for message %s → app %s",
                raw.provider_message_id,
                existing_msg.application_id,
            )
            return existing_msg.application_id, _METHOD_THREAD, _CONFIDENCE_THREAD

    # --- Stage 2: from_domain matches exactly one application's company domain ---
    domain_matches = [
        app
        for app in open_apps
        if company_domains.get(app.id, "").lower() == from_domain
    ]
    if len(domain_matches) == 1:
        logger.debug(
            "match_message: domain match for message %s → app %s",
            raw.provider_message_id,
            domain_matches[0].id,
        )
        return domain_matches[0].id, _METHOD_DOMAIN, _CONFIDENCE_DOMAIN

    # --- Stage 3: known ATS sender + single open app ---
    if from_domain in ATS_SENDER_DOMAINS and len(open_apps) == 1:
        logger.debug(
            "match_message: ATS sender match for message %s → app %s",
            raw.provider_message_id,
            open_apps[0].id,
        )
        return open_apps[0].id, _METHOD_ATS, _CONFIDENCE_ATS

    # --- Stage 4: LLM tie-break — ONLY when ambiguous (multiple domain matches) ---
    if len(domain_matches) > 1:
        logger.debug(
            "match_message: %d domain candidates, invoking LLM tie-break for message %s",
            len(domain_matches),
            raw.provider_message_id,
        )
        matched_id = await _llm_tie_break(session, llm, raw, domain_matches)
        if matched_id is not None:
            return matched_id, _METHOD_LLM, _CONFIDENCE_LLM_MATCH

    # --- No match ---
    return None, None, 0.0
