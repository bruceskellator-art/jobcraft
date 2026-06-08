"""API tests for admin PromptVersion endpoints.

Covers:
- GET /api/admin/prompts            Grouped by name; versions ordered desc
- GET /api/admin/prompts/{id}       Full detail including template
- GET /api/admin/prompts/{unknown}  404
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.prompt_version import PromptVersion
from app.main import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pv(
    name: str,
    version: int,
    *,
    is_active: bool = False,
    template: str = "Template for {{ name }} v{{ version }}.",
) -> PromptVersion:
    return PromptVersion(
        id=uuid.uuid4(),
        name=name,
        version=version,
        template=template,
        model="claude-3-haiku-20240307",
        temperature=0.5,
        is_active=is_active,
        metadata_={"author": "test"},
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def prompts_client(session: AsyncSession):
    """Test client with get_session overridden; seeds 2 names × 2 versions."""
    application = create_app()

    # 2 names × 2 versions = 4 PromptVersion rows
    pv_cover_v1 = _pv("cover_letter", 1)
    pv_cover_v2 = _pv(
        "cover_letter", 2, is_active=True, template="Better cover letter for {{ job }}."
    )
    pv_summary_v1 = _pv("job_summary", 1)
    pv_summary_v2 = _pv("job_summary", 2, is_active=True)

    session.add(pv_cover_v1)
    session.add(pv_cover_v2)
    session.add(pv_summary_v1)
    session.add(pv_summary_v2)
    await session.flush()

    async def _override_session():
        yield session

    application.dependency_overrides[get_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac, {
            "cover_v1": pv_cover_v1,
            "cover_v2": pv_cover_v2,
            "summary_v1": pv_summary_v1,
            "summary_v2": pv_summary_v2,
        }

    application.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: GET /api/admin/prompts
# ---------------------------------------------------------------------------


class TestListPromptsGrouped:
    async def test_returns_both_names(self, prompts_client) -> None:
        client, _ = prompts_client

        response = await client.get("/api/admin/prompts")

        assert response.status_code == 200
        body = response.json()
        assert "cover_letter" in body
        assert "job_summary" in body

    async def test_each_name_has_two_versions(self, prompts_client) -> None:
        client, _ = prompts_client

        response = await client.get("/api/admin/prompts")

        body = response.json()
        assert len(body["cover_letter"]) == 2
        assert len(body["job_summary"]) == 2

    async def test_versions_ordered_descending(self, prompts_client) -> None:
        client, _ = prompts_client

        response = await client.get("/api/admin/prompts")

        body = response.json()
        cover_versions = [v["version"] for v in body["cover_letter"]]
        assert cover_versions == sorted(cover_versions, reverse=True)

        summary_versions = [v["version"] for v in body["job_summary"]]
        assert summary_versions == sorted(summary_versions, reverse=True)

    async def test_list_view_excludes_template(self, prompts_client) -> None:
        """PromptVersionRead should not expose the template field."""
        client, _ = prompts_client

        response = await client.get("/api/admin/prompts")

        body = response.json()
        for versions in body.values():
            for item in versions:
                assert "template" not in item


# ---------------------------------------------------------------------------
# Tests: GET /api/admin/prompts/{id}
# ---------------------------------------------------------------------------


class TestGetPromptDetail:
    async def test_returns_template_and_metadata(self, prompts_client) -> None:
        client, seeds = prompts_client
        pv_id = str(seeds["cover_v2"].id)

        response = await client.get(f"/api/admin/prompts/{pv_id}")

        assert response.status_code == 200
        body = response.json()
        assert "template" in body
        assert body["template"] == "Better cover letter for {{ job }}."
        assert "metadata_" in body

    async def test_detail_contains_core_fields(self, prompts_client) -> None:
        client, seeds = prompts_client
        pv_id = str(seeds["cover_v2"].id)

        response = await client.get(f"/api/admin/prompts/{pv_id}")

        body = response.json()
        assert body["name"] == "cover_letter"
        assert body["version"] == 2
        assert body["is_active"] is True

    async def test_returns_404_for_unknown_id(self, prompts_client) -> None:
        client, _ = prompts_client
        unknown = str(uuid.uuid4())

        response = await client.get(f"/api/admin/prompts/{unknown}")

        assert response.status_code == 404
