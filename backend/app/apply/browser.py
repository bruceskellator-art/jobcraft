"""Browser automation layer for the Apply Engine.

FormSource is a Protocol; two implementations are provided:
- FakeFormSource: in-memory test double, no network I/O.
- PlaywrightFormSource: stub that raises NotImplementedError until the
  Playwright driver is wired in (a future task).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from app.apply.types import ApplyOutcome, FieldMap, FormField

if TYPE_CHECKING:
    from app.db.models.application import Application
    from app.db.models.job_posting import JobPosting

logger = logging.getLogger(__name__)


class FormSource(Protocol):
    """Protocol for extracting and submitting application forms."""

    async def render_form(
        self,
        job: JobPosting,
        app: Application,
    ) -> list[FormField]: ...

    async def has_captcha(
        self,
        job: JobPosting,
        app: Application,
    ) -> bool: ...

    async def submit_form(
        self,
        job: JobPosting,
        field_map: FieldMap,
    ) -> ApplyOutcome: ...


class FakeFormSource:
    """In-memory test double for FormSource.

    Canned fields are returned by render_form; submit_form records the call
    without touching a network. Pass captcha=True to simulate a CAPTCHA wall.
    """

    def __init__(
        self,
        fields: list[FormField],
        *,
        captcha: bool = False,
        dry_run: bool = True,
    ) -> None:
        self._fields = fields
        self._captcha = captcha
        self._dry_run = dry_run
        self.submitted_field_maps: list[FieldMap] = []

    async def render_form(
        self,
        job: JobPosting,
        app: Application,
    ) -> list[FormField]:
        return list(self._fields)

    async def has_captcha(
        self,
        job: JobPosting,
        app: Application,
    ) -> bool:
        """Return the captcha flag set at construction time."""
        return self._captcha

    async def submit_form(
        self,
        job: JobPosting,
        field_map: FieldMap,
    ) -> ApplyOutcome:
        if self._captcha:
            logger.warning("CAPTCHA detected — blocking application (job_id=%s)", job.id)
            return ApplyOutcome(
                outcome="blocked",
                blocked_reason="CAPTCHA / bot-wall detected; manual application required.",
            )
        self.submitted_field_maps.append(field_map)
        return ApplyOutcome(outcome="submitted")


class PlaywrightFormSource:
    """Real browser driver stub — NOT yet wired in this build.

    This stub exists so import paths and type signatures are stable.
    A future task will inject a Playwright browser context here and implement
    render_form / submit_form against live ATS pages using the user's own
    authenticated session.
    """

    async def render_form(
        self,
        job: JobPosting,
        app: Application,
    ) -> list[FormField]:
        raise NotImplementedError(
            "PlaywrightFormSource.render_form: Playwright driver not wired in this build. "
            "Use FakeFormSource for testing or implement the driver in a future phase."
        )

    async def has_captcha(
        self,
        job: JobPosting,
        app: Application,
    ) -> bool:
        """Playwright stub: returns False until driver is wired in."""
        return False

    async def submit_form(
        self,
        job: JobPosting,
        field_map: FieldMap,
    ) -> ApplyOutcome:
        raise NotImplementedError(
            "PlaywrightFormSource.submit_form: Playwright driver not wired in this build. "
            "Use FakeFormSource for testing or implement the driver in a future phase."
        )
