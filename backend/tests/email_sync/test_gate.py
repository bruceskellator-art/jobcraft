"""Tests for the confidence gate (decide_transition).

Key rules verified:
- forward + high confidence + not requires_human → apply
- backwards transition → propose (even if high confidence)
- low confidence → propose
- offer/rejected (requires_human=True) → ALWAYS propose, even high confidence + forward
"""
from __future__ import annotations

from app.email_sync.classifier import EmailStatusInference
from app.email_sync.gate import decide_transition


def _inference(
    *,
    classification: str = "phone_screen",
    confidence: float = 0.9,
    suggested_status: str = "phone_screen",
    evidence: str = "We'd like to schedule a call",
    requires_human: bool = False,
) -> EmailStatusInference:
    return EmailStatusInference(
        classification=classification,  # type: ignore[arg-type]
        confidence=confidence,
        suggested_status=suggested_status,
        evidence=evidence,
        requires_human=requires_human,
    )


class TestAutoApply:
    def test_forward_high_confidence_not_human_returns_apply(self) -> None:
        # submitted → phone_screen is clearly forward, high confidence, not human
        inf = _inference(
            classification="phone_screen",
            confidence=0.92,
            suggested_status="phone_screen",
            requires_human=False,
        )
        decision, status = decide_transition(inf, "submitted")
        assert decision == "apply"
        assert status == "phone_screen"

    def test_submitted_to_technical_is_forward(self) -> None:
        inf = _inference(
            classification="technical",
            confidence=0.88,
            suggested_status="technical",
            requires_human=False,
        )
        decision, _ = decide_transition(inf, "submitted")
        assert decision == "apply"

    def test_phone_screen_to_onsite_is_forward(self) -> None:
        inf = _inference(
            classification="onsite",
            confidence=0.95,
            suggested_status="onsite",
            requires_human=False,
        )
        decision, _ = decide_transition(inf, "phone_screen")
        assert decision == "apply"


class TestProposedBackwards:
    def test_backwards_transition_returns_propose(self) -> None:
        # phone_screen → submitted is backwards
        inf = _inference(
            classification="acknowledged",
            confidence=0.95,
            suggested_status="submitted",
            requires_human=False,
        )
        decision, _ = decide_transition(inf, "phone_screen")
        assert decision == "propose"

    def test_same_status_lateral_returns_propose(self) -> None:
        # submitted → submitted is lateral (not forward)
        inf = _inference(
            classification="acknowledged",
            confidence=0.95,
            suggested_status="submitted",
            requires_human=False,
        )
        decision, _ = decide_transition(inf, "submitted")
        assert decision == "propose"


class TestProposedLowConfidence:
    def test_low_confidence_returns_propose(self) -> None:
        inf = _inference(
            classification="phone_screen",
            confidence=0.50,
            suggested_status="phone_screen",
            requires_human=False,
        )
        decision, _ = decide_transition(inf, "submitted")
        assert decision == "propose"

    def test_exactly_at_threshold_returns_apply(self) -> None:
        inf = _inference(
            classification="phone_screen",
            confidence=0.75,  # == default threshold
            suggested_status="phone_screen",
            requires_human=False,
        )
        decision, _ = decide_transition(inf, "submitted")
        assert decision == "apply"

    def test_just_below_threshold_returns_propose(self) -> None:
        inf = _inference(
            classification="phone_screen",
            confidence=0.74,
            suggested_status="phone_screen",
            requires_human=False,
        )
        decision, _ = decide_transition(inf, "submitted")
        assert decision == "propose"


class TestProposedHighStakes:
    def test_offer_always_proposes_even_high_confidence_forward(self) -> None:
        # offer is forward from submitted, high confidence, but requires_human=True
        inf = _inference(
            classification="offer",
            confidence=0.99,
            suggested_status="offer",
            requires_human=True,
        )
        decision, _ = decide_transition(inf, "submitted")
        assert decision == "propose"

    def test_rejected_always_proposes(self) -> None:
        inf = _inference(
            classification="rejected",
            confidence=0.99,
            suggested_status="rejected",
            requires_human=True,
        )
        decision, _ = decide_transition(inf, "onsite")
        assert decision == "propose"

    def test_requires_human_true_overrides_forward_and_high_confidence(self) -> None:
        # Even if requires_human=True but classification is not offer/rejected
        # (edge case): still propose because requires_human=True.
        inf = _inference(
            classification="phone_screen",
            confidence=0.99,
            suggested_status="phone_screen",
            requires_human=True,  # hypothetical override
        )
        decision, _ = decide_transition(inf, "submitted")
        assert decision == "propose"


class TestProposedUnknownStatuses:
    def test_unknown_current_status_returns_propose(self) -> None:
        inf = _inference(
            classification="phone_screen",
            confidence=0.95,
            suggested_status="phone_screen",
            requires_human=False,
        )
        # "auto_filling" is not in STATUS_ORDER
        decision, _ = decide_transition(inf, "auto_filling")
        assert decision == "propose"

    def test_unknown_suggested_status_returns_propose(self) -> None:
        inf = _inference(
            classification="other",
            confidence=0.95,
            suggested_status="unknown_stage",
            requires_human=False,
        )
        decision, _ = decide_transition(inf, "submitted")
        assert decision == "propose"


class TestSuggestedStatusPassthrough:
    def test_suggested_status_always_returned(self) -> None:
        inf = _inference(
            classification="rejected",
            confidence=0.99,
            suggested_status="rejected",
            requires_human=True,
        )
        decision, status = decide_transition(inf, "onsite")
        assert status == "rejected"
        assert decision == "propose"
