from __future__ import annotations

import io
import json

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.deps import get_llm_client
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.main import create_app

# ---------------------------------------------------------------------------
# Canned LLM response (2 items)
# ---------------------------------------------------------------------------

_CANNED_ITEMS = [
    {
        "kind": "work",
        "title": "Backend Engineer",
        "organization": "TechCorp",
        "content": "Designed REST APIs.",
        "start_date": "2021-03",
        "end_date": "2024-01",
        "tags": ["python"],
    },
    {
        "kind": "education",
        "title": "M.Sc. Computer Science",
        "organization": "Tech University",
        "content": "Thesis on distributed systems.",
        "start_date": "2019-09",
        "end_date": "2021-02",
        "tags": [],
    },
]
_CANNED_RESPONSE = json.dumps({"items": _CANNED_ITEMS})


def _make_minimal_pdf() -> bytes:
    """Generate a minimal valid single-page PDF with extractable text using pypdf."""
    from pypdf import PdfWriter
    from pypdf.generic import (
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
    )

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    # Build a minimal content stream with a text operator
    content_stream = DecodedStreamObject()
    content_stream.set_data(b"BT /F1 12 Tf 100 700 Td (Sample Resume Text) Tj ET")

    # Wire a basic font resource so the content stream is valid
    font_dict = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    resources = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font_dict}
            )
        }
    )
    page[NameObject("/Resources")] = resources  # type: ignore[index]
    page[NameObject("/Contents")] = content_stream  # type: ignore[index]

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(session: AsyncSession):  # type: ignore[misc]
    """Test client with session, get_current_user, and get_llm_client all overridden."""
    application = create_app()

    async def _override_session():  # type: ignore[return]
        yield session

    # Dev user is created automatically by get_current_user via the session override.
    application.dependency_overrides[get_session] = _override_session

    mock_adapter = MockAdapter(fn=lambda _prompt: _CANNED_RESPONSE)

    def _override_llm(session: AsyncSession = None):  # type: ignore[assignment]
        return LLMClient(session=session, adapter=mock_adapter)

    # Use a closure so the overridden session flows into LLMClient
    async def _session_for_llm():  # type: ignore[return]
        yield session

    def _llm_override():
        return LLMClient(session=session, adapter=mock_adapter)

    application.dependency_overrides[get_llm_client] = _llm_override

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac

    application.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestImportResumeEndpoint:
    """POST /api/experience/import"""

    async def test_valid_pdf_returns_200_with_created_items(
        self, client: AsyncClient
    ) -> None:
        # Arrange
        pdf_bytes = _make_minimal_pdf()

        # Act
        response = await client.post(
            "/api/experience/import",
            files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        assert "created" in body
        assert len(body["created"]) == 2

    async def test_valid_pdf_returns_correct_item_fields(
        self, client: AsyncClient
    ) -> None:
        # Arrange
        pdf_bytes = _make_minimal_pdf()

        # Act
        response = await client.post(
            "/api/experience/import",
            files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        )

        # Assert
        body = response.json()
        items = body["created"]
        assert items[0]["kind"] == "work"
        assert items[0]["title"] == "Backend Engineer"
        assert items[1]["kind"] == "education"
        assert items[1]["organization"] == "Tech University"

    async def test_non_pdf_content_type_returns_415(
        self, client: AsyncClient
    ) -> None:
        # Arrange
        text_bytes = b"This is not a PDF"

        # Act
        response = await client.post(
            "/api/experience/import",
            files={"file": ("resume.txt", text_bytes, "text/plain")},
        )

        # Assert
        assert response.status_code == 415

    async def test_missing_file_returns_422(self, client: AsyncClient) -> None:
        # Arrange — no file uploaded

        # Act
        response = await client.post("/api/experience/import")

        # Assert
        assert response.status_code == 422
