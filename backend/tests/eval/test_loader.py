"""Unit tests for app.eval.loader."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from app.eval.loader import load_fixture_json, load_suite
from app.eval.types import EvalSuite

# ---------------------------------------------------------------------------
# load_suite
# ---------------------------------------------------------------------------


class TestLoadSuite:
    def test_loads_valid_suite(self, tmp_path: Path) -> None:
        yaml_content = textwrap.dedent("""\
            name: test_suite
            description: A test suite
            cases:
              - id: case_001
                assertions:
                  - kind: contains_skill
                    skill: Python
                  - kind: length
                    min_words: 50
                    max_words: 500
        """)
        suite_file = tmp_path / "test_suite.yaml"
        suite_file.write_text(yaml_content)

        suite = load_suite(suite_file)

        assert isinstance(suite, EvalSuite)
        assert suite.name == "test_suite"
        assert len(suite.cases) == 1
        assert suite.cases[0].id == "case_001"
        assert len(suite.cases[0].assertions) == 2

    def test_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            load_suite(tmp_path / "nonexistent.yaml")

    def test_raises_on_missing_required_field(self, tmp_path: Path) -> None:
        # name is required — omit it
        yaml_content = textwrap.dedent("""\
            description: Missing name
            cases: []
        """)
        suite_file = tmp_path / "bad.yaml"
        suite_file.write_text(yaml_content)

        with pytest.raises(ValueError, match="Invalid suite schema"):
            load_suite(suite_file)

    def test_raises_on_bad_assertion_kind(self, tmp_path: Path) -> None:
        yaml_content = textwrap.dedent("""\
            name: bad_suite
            cases:
              - id: case_001
                assertions:
                  - kind: nonexistent_kind
                    skill: Python
        """)
        suite_file = tmp_path / "bad_kind.yaml"
        suite_file.write_text(yaml_content)

        with pytest.raises(ValueError, match="Invalid suite schema"):
            load_suite(suite_file)

    def test_loads_suite_with_no_cases(self, tmp_path: Path) -> None:
        yaml_content = "name: empty_suite\ncases: []\n"
        suite_file = tmp_path / "empty.yaml"
        suite_file.write_text(yaml_content)

        suite = load_suite(suite_file)
        assert suite.name == "empty_suite"
        assert suite.cases == []

    def test_raises_on_non_mapping_yaml(self, tmp_path: Path) -> None:
        suite_file = tmp_path / "list.yaml"
        suite_file.write_text("- item1\n- item2\n")

        with pytest.raises(ValueError, match="YAML mapping"):
            load_suite(suite_file)


# ---------------------------------------------------------------------------
# load_fixture_json
# ---------------------------------------------------------------------------


class TestLoadFixtureJson:
    def test_loads_valid_json(self, tmp_path: Path) -> None:
        data = {"experience_items": [{"kind": "work", "content": "Worked at ACME."}]}
        fixture_file = tmp_path / "user.json"
        fixture_file.write_text(json.dumps(data))

        result = load_fixture_json(fixture_file)

        assert result == data

    def test_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            load_fixture_json(tmp_path / "missing.json")

    def test_raises_on_invalid_json(self, tmp_path: Path) -> None:
        fixture_file = tmp_path / "bad.json"
        fixture_file.write_text("not valid json {{{")

        with pytest.raises(ValueError, match="Invalid JSON"):
            load_fixture_json(fixture_file)

    def test_raises_when_json_not_dict(self, tmp_path: Path) -> None:
        fixture_file = tmp_path / "list.json"
        fixture_file.write_text(json.dumps([1, 2, 3]))

        with pytest.raises(ValueError, match="JSON object"):
            load_fixture_json(fixture_file)
