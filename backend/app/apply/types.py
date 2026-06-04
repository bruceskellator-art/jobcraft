from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

KNOCKOUT_KEYS: frozenset[str] = frozenset(
    {"work_authorization", "visa_status", "citizenship", "years_of_experience"}
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
