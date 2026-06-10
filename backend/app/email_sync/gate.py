"""Confidence gate — decides whether to auto-apply or propose a status transition.

Rules (spec §4.9):
- AUTO-APPLY when:
    1. confidence >= threshold (default 0.75)
    2. suggested_status moves the application FORWARD monotonically
    3. requires_human is False
- PROPOSE in all other cases:
    - low confidence
    - backwards / lateral / skip transition
    - requires_human=True (offer, rejected — always confirm)

This is a pure function; no I/O, no side effects.
"""
from __future__ import annotations

from typing import Literal

from app.email_sync.classifier import EmailStatusInference

# Status order for monotonic-forward check.
# Statuses not in this map are treated as terminal / unordered.
STATUS_ORDER: dict[str, int] = {
    "interested": 0,
    "queued": 1,
    "submitted": 2,
    "phone_screen": 3,
    "technical": 4,
    "onsite": 5,
    "offer": 6,
    # terminal statuses: no order (omitted so they always go to propose path)
    # "rejected": terminal
    # "withdrawn": terminal
}

_DEFAULT_CONFIDENCE_THRESHOLD = 0.75

Decision = Literal["apply", "propose"]


def decide_transition(
    inference: EmailStatusInference,
    current_status: str,
    *,
    confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
) -> tuple[Decision, str]:
    """Decide whether to auto-apply or propose a status transition.

    Args:
        inference: The classifier output (EmailStatusInference).
        current_status: The application's current status string.
        confidence_threshold: Minimum confidence to consider auto-apply.
            Defaults to 0.75.

    Returns:
        ("apply", suggested_status) — safe to apply automatically, OR
        ("propose", suggested_status) — surface to user for one-tap confirm.
    """
    suggested = inference.suggested_status

    # Rule 1: high-stakes classifications always require human confirmation.
    if inference.requires_human:
        return "propose", suggested

    # Rule 2: confidence gate.
    if inference.confidence < confidence_threshold:
        return "propose", suggested

    # Rule 3: monotonic-forward check.
    # If either status is not in STATUS_ORDER (e.g. rejected, withdrawn,
    # auto_filling, etc.), we cannot guarantee forward movement → propose.
    current_order = STATUS_ORDER.get(current_status)
    suggested_order = STATUS_ORDER.get(suggested)

    if current_order is None or suggested_order is None:
        return "propose", suggested

    if suggested_order <= current_order:
        # lateral or backwards transition → propose
        return "propose", suggested

    # All conditions met — safe to apply automatically.
    return "apply", suggested
