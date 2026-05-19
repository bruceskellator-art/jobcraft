from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.db.models.prompt_version import PromptVersion
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.services.resume_extract import (
    ensure_extraction_prompt,
    import_resume_from_text,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CANNED_ITEMS = [
    {
        "kind": "work",
        "title": "Software Engineer",
        "organization": "Acme Corp",
        "content": "Built scalable microservices.",
        "start_date": "2020-01",
        "end_date": "2023-06",
        "tags": ["python", "fastapi"],
    },
    {
        "kind": "project",
        "title": "Open Source CLI",
        "organization": "",
        "content": "Authored a popular CLI tool.",
        "start_date": None,
        "end_date": None,
        "tags": ["cli", "rust"],
    },
    {
        "kind": "education",
        "title": "B.Sc. Computer Science",
        "organization": "State University",
        "content": "Graduated with honours.",
        "start_date": "2016-09",
        "end_date": "2020-05",
        "tags": [],
    },
]

_CANNED_RESPONSE = json.dumps({"items": _CANNED_ITEMS})


def _make_mock_llm(session) -> tuple[LLMClient, MockAdapter]:
    adapter = MockAdapter(responses=[_CANNED_RESPONSE])
    client = LLMClient(session=session, adapter=adapter)
    return client, adapter


# ---------------------------------------------------------------------------
# Test: ensure_extraction_prompt is idempotent
# ---------------------------------------------------------------------------


class TestEnsureExtractionPrompt:
    """ensure_extraction_prompt must create-or-get without duplicating active rows."""

    async def test_creates_prompt_on_first_call(self, session) -> None:
        # Arrange — empty DB

        # Act
        prompt = await ensure_extraction_prompt(session)

        # Assert
        assert prompt.name == "extract_resume"
        assert prompt.version == 1
        assert prompt.is_active is True
        assert "{{ resume_text }}" in prompt.template

    async def test_returns_same_row_on_second_call(self, session) -> None:
        # Arrange — call once to seed
        first = await ensure_extraction_prompt(session)

        # Act — call again
        second = await ensure_extraction_prompt(session)

        # Assert — same DB row, no duplicate
        assert first.id == second.id

    async def test_does_not_insert_duplicate_active_version(self, session) -> None:
        # Arrange
        await ensure_extraction_prompt(session)
        await ensure_extraction_prompt(session)

        # Assert — only one active row for this name
        result = await session.execute(
            select(PromptVersion).where(
                PromptVersion.name == "extract_resume",
                PromptVersion.is_active == True,  # noqa: E712
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Test: import_resume_from_text persists correct items
# ---------------------------------------------------------------------------


class TestImportResumeFromText:
    """import_resume_from_text should persist each extracted item correctly."""

    async def test_persists_correct_number_of_items(self, session) -> None:
        # Arrange
        llm, _ = _make_mock_llm(session)
        user_id = uuid.uuid4()

        # Act
        created = await import_resume_from_text(
            session=session,
            llm=llm,
            user_id=user_id,
            resume_text="Alice worked at Acme Corp...",
        )

        # Assert
        assert len(created) == 3

    async def test_persists_correct_kind_and_content(self, session) -> None:
        # Arrange
        llm, _ = _make_mock_llm(session)
        user_id = uuid.uuid4()

        # Act
        created = await import_resume_from_text(
            session=session,
            llm=llm,
            user_id=user_id,
            resume_text="Some resume text.",
        )

        # Assert — kinds match canned data
        kinds = [item.kind for item in created]
        assert kinds == ["work", "project", "education"]

        work_item = created[0]
        assert work_item.title == "Software Engineer"
        assert work_item.organization == "Acme Corp"
        assert work_item.content == "Built scalable microservices."

    async def test_persists_tags(self, session) -> None:
        # Arrange
        llm, _ = _make_mock_llm(session)
        user_id = uuid.uuid4()

        # Act
        created = await import_resume_from_text(
            session=session,
            llm=llm,
            user_id=user_id,
            resume_text="Resume with skills.",
        )

        # Assert — tags on work item
        assert created[0].tags == ["python", "fastapi"]
        # project item has tags
        assert created[1].tags == ["cli", "rust"]

    async def test_all_items_belong_to_correct_user(self, session) -> None:
        # Arrange
        llm, _ = _make_mock_llm(session)
        user_id = uuid.uuid4()

        # Act
        created = await import_resume_from_text(
            session=session,
            llm=llm,
            user_id=user_id,
            resume_text="Resume text.",
        )

        # Assert
        for item in created:
            assert item.user_id == user_id

    async def test_empty_text_raises_value_error(self, session) -> None:
        # Arrange
        llm, _ = _make_mock_llm(session)
        user_id = uuid.uuid4()

        # Act / Assert
        with pytest.raises(ValueError, match="empty"):
            await import_resume_from_text(
                session=session,
                llm=llm,
                user_id=user_id,
                resume_text="",
            )

    async def test_whitespace_only_text_raises_value_error(self, session) -> None:
        # Arrange
        llm, _ = _make_mock_llm(session)
        user_id = uuid.uuid4()

        # Act / Assert
        with pytest.raises(ValueError, match="empty"):
            await import_resume_from_text(
                session=session,
                llm=llm,
                user_id=user_id,
                resume_text="   \n\t  ",
            )
