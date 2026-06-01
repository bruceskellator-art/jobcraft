"""Load and validate eval suites and fixture files from disk."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.eval.types import EvalSuite


def load_suite(path: str | Path) -> EvalSuite:
    """Parse and validate a YAML suite file.

    Raises FileNotFoundError if path does not exist.
    Raises ValueError with a descriptive message on schema violations.
    """
    suite_path = Path(path)
    if not suite_path.exists():
        raise FileNotFoundError(f"Suite file not found: {suite_path}")

    raw = suite_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(
            f"Suite file must be a YAML mapping, got {type(data).__name__}: {suite_path}"
        )

    try:
        return EvalSuite.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid suite schema in {suite_path}:\n{exc}") from exc


def load_fixture_json(path: str | Path) -> dict:
    """Load a JSON fixture file.

    Raises FileNotFoundError if path does not exist.
    Raises ValueError if the file is not valid JSON or not a dict.
    """
    fixture_path = Path(path)
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture file not found: {fixture_path}")

    raw = fixture_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in fixture {fixture_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Fixture must be a JSON object, got {type(data).__name__}: {fixture_path}"
        )

    return data
