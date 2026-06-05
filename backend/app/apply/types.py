from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

KNOCKOUT_KEYS: frozenset[str] = frozenset(
    {"work_authorization", "visa_status", "citizenship", "years_of_experience"}
)

# Status values that may be set via the manual PATCH /applications/{id}/status endpoint.
# Shared between apply_orchestration and the API router to avoid drift.
ALLOWED_MANUAL_STATUSES: frozenset[str] = frozenset(
    {
        "interested",
        "queued",
        "needs_review",
        "phone_screen",
        "technical",
        "onsite",
        "offer",
        "rejected",
        "withdrawn",
    }
)


class FormField(BaseModel):
    name: str
    label: str
    field_type: Literal["text", "email", "tel", "select", "textarea", "checkbox", "file"]
    options: list[str] = Field(default_factory=list)
    required: bool = False
    is_knockout: bool = False


class MappedField(BaseModel):
    field: FormField
    value: str | None
    source: Literal["profile", "answer_bank", "cover_letter", "generated", "none"]
    confidence: float


class FieldMap(BaseModel):
    """Mapping of form fields to values.

    overall_confidence is the MEAN of per-field confidences.
    A single knockout field with missing value (confidence=0.0) therefore drags
    the overall score toward 0, making the gate conservative by default.
    Mean is preferred over min because it reflects aggregate quality rather
    than a single worst case that might be a non-critical optional field.

    NOTE: the mean confidence alone does NOT protect against knockout fields —
    a form with many high-confidence trivial fields could still pass the
    confidence threshold even with an unresolved knockout.  The real knockout
    safety mechanism is ``has_unresolved_knockout`` checked in
    ``apply_orchestration.process_application`` and enforced by ``gate.decide``.
    """

    fields: list[MappedField]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def overall_confidence(self) -> float:
        if not self.fields:
            return 0.0
        return sum(f.confidence for f in self.fields) / len(self.fields)


class ApplyOutcome(BaseModel):
    outcome: Literal["submitted", "queued", "blocked", "failed"]
    blocked_reason: str | None = None
    screenshot_path: str | None = None


class GateDecision(BaseModel):
    decision: Literal["auto_submit", "review", "block"]
    reason: str
