"""Eval framework domain types: assertions, cases, suites, and results."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Assertion definitions (discriminated union on kind)
# ---------------------------------------------------------------------------


class ContainsSkillAssertion(BaseModel):
    kind: Literal["contains_skill"] = "contains_skill"
    skill: str


class ExcludesPhraseAssertion(BaseModel):
    kind: Literal["excludes_phrase"] = "excludes_phrase"
    phrase: str


class LengthAssertion(BaseModel):
    kind: Literal["length"] = "length"
    min_words: int | None = None
    max_words: int | None = None


class GroundednessAssertion(BaseModel):
    kind: Literal["groundedness"] = "groundedness"
    threshold: float = Field(ge=0.0, le=1.0)


class LlmJudgeAssertion(BaseModel):
    kind: Literal["llm_judge"] = "llm_judge"
    rubric: str
    threshold: float = Field(ge=0.0, le=1.0)


Assertion = Annotated[
    ContainsSkillAssertion
    | ExcludesPhraseAssertion
    | LengthAssertion
    | GroundednessAssertion
    | LlmJudgeAssertion,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Eval case and suite
# ---------------------------------------------------------------------------


class EvalCase(BaseModel):
    id: str
    user_corpus: str | None = None  # path to fixture JSON relative to eval/
    job: str | None = None  # path to fixture JSON relative to eval/
    assertions: list[Assertion] = Field(default_factory=list)


class EvalSuite(BaseModel):
    name: str
    description: str = ""
    cases: list[EvalCase] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class AssertionResult(BaseModel):
    kind: str
    passed: bool
    score: float | None = None
    detail: str = ""


class CaseResult(BaseModel):
    case_id: str
    passed: bool
    score: float | None = None
    assertions: list[AssertionResult] = Field(default_factory=list)


class SuiteResult(BaseModel):
    suite_name: str
    passed: bool
    cases: list[CaseResult] = Field(default_factory=list)
    aggregate: dict[str, float] = Field(default_factory=dict)
