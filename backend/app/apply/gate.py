"""Confidence gate — decides whether to auto-submit, queue for review, or block.

This is a PURE function: no I/O, no side effects.  All safety rules from §4.8
of the JobCraft spec are enforced here:

BLOCK conditions (hard stops, checked first):
  1. CAPTCHA / bot-wall detected.

REVIEW conditions (checked in order):
  2. Autopilot mode is "off".
  3. Mode is "selective" AND the job source is not in auto_submit_sources.
  4. overall_confidence < min_confidence.
  5. match_score is provided AND match_score < min_fit.
  6. has_unresolved_knockout is True.

AUTO_SUBMIT: all conditions above are clear.

Note: mode="full" relaxes the source allowlist check (condition 3) but does NOT
relax confidence, fit, or knockout guards.
"""

from __future__ import annotations

from app.apply.types import FieldMap, GateDecision
from app.services.autopilot import AutopilotConfig


def decide(
    field_map: FieldMap,
    job: object,  # JobPosting at runtime; kept as object to avoid circular import
    *,
    autopilot: AutopilotConfig,
    match_score: float | None,
    source: str,
    captcha: bool,
    has_unresolved_knockout: bool,
) -> GateDecision:
    """Return a GateDecision for a single application attempt.

    Parameters
    ----------
    field_map:
        The resolved field mapping including overall_confidence.
    job:
        The JobPosting; not inspected here (source is passed explicitly).
    autopilot:
        User's autopilot configuration.
    match_score:
        Optional pre-computed fit score; None means unknown (not treated as failure).
    source:
        The job source string (e.g. "linkedin_easy_apply", "greenhouse").
    captcha:
        True if the form page has a CAPTCHA / bot-wall.
    has_unresolved_knockout:
        True if any knockout field has value=None.
    """
    # BLOCK: CAPTCHA — hard stop, never bypass.
    if captcha:
        return GateDecision(
            decision="block",
            reason="CAPTCHA / bot-wall detected; manual application required.",
        )

    # REVIEW: autopilot is off.
    if autopilot.mode == "off":
        return GateDecision(
            decision="review",
            reason="Autopilot mode is 'off'; all applications require manual review.",
        )

    # REVIEW: selective mode and source not in allowlist.
    if autopilot.mode == "selective" and source not in autopilot.auto_submit_sources:
        return GateDecision(
            decision="review",
            reason=(
                f"Source '{source}' is not in the auto-submit allowlist "
                f"({autopilot.auto_submit_sources}) for selective mode."
            ),
        )

    # REVIEW: confidence below threshold.
    if field_map.overall_confidence < autopilot.min_confidence:
        return GateDecision(
            decision="review",
            reason=(
                f"Overall confidence {field_map.overall_confidence:.2f} is below "
                f"the minimum threshold {autopilot.min_confidence:.2f}."
            ),
        )

    # REVIEW: match score below minimum fit.
    if match_score is not None and match_score < autopilot.min_fit:
        return GateDecision(
            decision="review",
            reason=(
                f"Match score {match_score:.2f} is below the minimum fit "
                f"threshold {autopilot.min_fit:.2f}."
            ),
        )

    # REVIEW: unresolved knockout field.
    if has_unresolved_knockout:
        return GateDecision(
            decision="review",
            reason=(
                "One or more knockout fields (work authorization, visa status, "
                "citizenship, years of experience) could not be resolved from the "
                "user profile. Manual review required."
            ),
        )

    return GateDecision(
        decision="auto_submit",
        reason="All safety checks passed; application is cleared for auto-submission.",
    )
