"""Pure-function truth table tests for the confidence gate."""

from __future__ import annotations

from app.apply.gate import decide
from app.apply.types import FieldMap, FormField, MappedField
from app.services.autopilot import AutopilotConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _field_map(confidence: float) -> FieldMap:
    """Build a minimal FieldMap with the given per-field confidence."""
    field = FormField(name="email", label="Email", field_type="email")
    mf = MappedField(
        field=field, value="test@example.com", source="profile", confidence=confidence
    )
    return FieldMap(fields=[mf])


def _default_config(**overrides: object) -> AutopilotConfig:
    defaults: dict[str, object] = {
        "mode": "selective",
        "auto_submit_sources": ["linkedin_easy_apply", "mycareersfuture"],
        "min_confidence": 0.75,
        "min_fit": 0.55,
        "daily_cap": 80,
    }
    defaults.update(overrides)
    return AutopilotConfig(**defaults)  # type: ignore[arg-type]


class _FakeJob:
    """Minimal job stand-in for the gate (gate does not inspect job directly)."""

    source = "linkedin_easy_apply"


_JOB = _FakeJob()


# ---------------------------------------------------------------------------
# BLOCK cases
# ---------------------------------------------------------------------------


def test_captcha_always_blocks() -> None:
    cfg = _default_config()
    result = decide(
        _field_map(1.0),
        _JOB,
        autopilot=cfg,
        match_score=1.0,
        source="linkedin_easy_apply",
        captcha=True,
        has_unresolved_knockout=False,
    )
    assert result.decision == "block"
    assert "captcha" in result.reason.lower()


# ---------------------------------------------------------------------------
# REVIEW cases
# ---------------------------------------------------------------------------


def test_mode_off_always_reviews() -> None:
    cfg = _default_config(mode="off")
    result = decide(
        _field_map(1.0),
        _JOB,
        autopilot=cfg,
        match_score=1.0,
        source="linkedin_easy_apply",
        captcha=False,
        has_unresolved_knockout=False,
    )
    assert result.decision == "review"
    assert "off" in result.reason.lower()


def test_source_not_allowlisted_selective_reviews() -> None:
    cfg = _default_config(mode="selective")
    result = decide(
        _field_map(1.0),
        _JOB,
        autopilot=cfg,
        match_score=1.0,
        source="workday",  # not in allowlist
        captcha=False,
        has_unresolved_knockout=False,
    )
    assert result.decision == "review"
    assert "allowlist" in result.reason.lower() or "workday" in result.reason.lower()


def test_low_confidence_reviews() -> None:
    cfg = _default_config(min_confidence=0.75)
    result = decide(
        _field_map(0.5),  # below 0.75
        _JOB,
        autopilot=cfg,
        match_score=1.0,
        source="linkedin_easy_apply",
        captcha=False,
        has_unresolved_knockout=False,
    )
    assert result.decision == "review"
    assert "confidence" in result.reason.lower()


def test_low_fit_score_reviews() -> None:
    cfg = _default_config(min_fit=0.55)
    result = decide(
        _field_map(1.0),
        _JOB,
        autopilot=cfg,
        match_score=0.3,  # below 0.55
        source="linkedin_easy_apply",
        captcha=False,
        has_unresolved_knockout=False,
    )
    assert result.decision == "review"
    assert "match" in result.reason.lower() or "fit" in result.reason.lower()


def test_unresolved_knockout_reviews() -> None:
    cfg = _default_config()
    result = decide(
        _field_map(1.0),
        _JOB,
        autopilot=cfg,
        match_score=1.0,
        source="linkedin_easy_apply",
        captcha=False,
        has_unresolved_knockout=True,
    )
    assert result.decision == "review"
    assert "knockout" in result.reason.lower()


# ---------------------------------------------------------------------------
# AUTO_SUBMIT case
# ---------------------------------------------------------------------------


def test_all_clear_auto_submits() -> None:
    cfg = _default_config(mode="selective")
    result = decide(
        _field_map(1.0),
        _JOB,
        autopilot=cfg,
        match_score=0.8,
        source="linkedin_easy_apply",
        captcha=False,
        has_unresolved_knockout=False,
    )
    assert result.decision == "auto_submit"


# ---------------------------------------------------------------------------
# mode="full" relaxes ONLY the source allowlist gate
# ---------------------------------------------------------------------------


def test_mode_full_relaxes_source_gate() -> None:
    """mode=full should auto-submit even for a source not in the allowlist."""
    cfg = _default_config(mode="full")
    result = decide(
        _field_map(1.0),
        _JOB,
        autopilot=cfg,
        match_score=0.8,
        source="workday",  # would be rejected in selective mode
        captcha=False,
        has_unresolved_knockout=False,
    )
    assert result.decision == "auto_submit"


def test_mode_full_still_blocks_captcha() -> None:
    """mode=full does NOT bypass CAPTCHA."""
    cfg = _default_config(mode="full")
    result = decide(
        _field_map(1.0),
        _JOB,
        autopilot=cfg,
        match_score=0.8,
        source="workday",
        captcha=True,
        has_unresolved_knockout=False,
    )
    assert result.decision == "block"


def test_mode_full_still_reviews_low_confidence() -> None:
    """mode=full does NOT relax the confidence gate."""
    cfg = _default_config(mode="full", min_confidence=0.75)
    result = decide(
        _field_map(0.4),
        _JOB,
        autopilot=cfg,
        match_score=0.8,
        source="workday",
        captcha=False,
        has_unresolved_knockout=False,
    )
    assert result.decision == "review"


def test_mode_full_still_reviews_unresolved_knockout() -> None:
    """mode=full does NOT bypass the knockout safety rule."""
    cfg = _default_config(mode="full")
    result = decide(
        _field_map(1.0),
        _JOB,
        autopilot=cfg,
        match_score=0.8,
        source="workday",
        captcha=False,
        has_unresolved_knockout=True,
    )
    assert result.decision == "review"


def test_none_match_score_does_not_trigger_review() -> None:
    """match_score=None means unknown; should not block auto-submit."""
    cfg = _default_config()
    result = decide(
        _field_map(1.0),
        _JOB,
        autopilot=cfg,
        match_score=None,
        source="linkedin_easy_apply",
        captcha=False,
        has_unresolved_knockout=False,
    )
    assert result.decision == "auto_submit"
