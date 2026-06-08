"""API tests for admin LlmCall observability endpoints.

Covers:
- GET  /api/admin/calls                    List (all, model filter, prompt_version filter)
- GET  /api/admin/calls/cost               by_day + totals; tolerates NULL cost
- GET  /api/admin/calls/{call_id}          full detail including rendered_prompt
- GET  /api/admin/calls/{unknown_id}       404
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models.llm_call import LlmCall
from app.db.models.prompt_version import PromptVersion
from app.main import create_app

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)  # noqa: UP017


def _pv(name: str = "cover_letter", version: int = 1) -> PromptVersion:
    return PromptVersion(
        id=uuid.uuid4(),
        name=name,
        version=version,
        template="Write a cover letter for {{ job_title }}.",
        model="claude-3-haiku-20240307",
        temperature=0.7,
        is_active=True,
    )


def _call(
    pv_id: uuid.UUID,
    *,
    model: str = "claude-3-haiku-20240307",
    cost_usd: Decimal | None = Decimal("0.001234"),
    latency_ms: int | None = 1200,
    error: str | None = None,
) -> LlmCall:
    return LlmCall(
        id=uuid.uuid4(),
        prompt_version_id=pv_id,
        inputs={"job_title": "Backend Engineer"},
        rendered_prompt="Write a cover letter for Backend Engineer.",
        response="Dear Hiring Manager, ...",
        parsed_response={"text": "Dear Hiring Manager, ..."},
        model=model,
        input_tokens=100,
        output_tokens=200,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        error=error,
        called_at=_NOW,
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def calls_client(session: AsyncSession):
    """Test client with get_session overridden to the shared in-memory session."""
    application = create_app()

    # Seed: one PromptVersion + several LlmCall rows
    pv1 = _pv(name="cover_letter", version=1)
    pv2 = _pv(name="cover_letter", version=2)
    pv2.is_active = False
    session.add(pv1)
    session.add(pv2)

    call_normal = _call(
        pv1.id, model="claude-3-haiku-20240307", cost_usd=Decimal("0.001"), latency_ms=1000
    )
    call_opus = _call(
        pv1.id, model="claude-opus-4-5", cost_usd=Decimal("0.010"), latency_ms=2000
    )
    call_error = _call(
        pv1.id,
        model="claude-3-haiku-20240307",
        cost_usd=Decimal("0.001"),
        latency_ms=500,
        error="timeout",
    )
    call_null_cost = _call(
        pv2.id, model="claude-3-haiku-20240307", cost_usd=None, latency_ms=None
    )

    session.add(call_normal)
    session.add(call_opus)
    session.add(call_error)
    session.add(call_null_cost)
    await session.flush()

    async def _override_session():
        yield session

    application.dependency_overrides[get_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        yield ac, {
            "pv1": pv1,
            "pv2": pv2,
            "call_normal": call_normal,
            "call_opus": call_opus,
            "call_error": call_error,
            "call_null_cost": call_null_cost,
        }

    application.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: GET /api/admin/calls
# ---------------------------------------------------------------------------


class TestListCalls:
    async def test_returns_all_calls_by_default(self, calls_client) -> None:
        client, seeds = calls_client

        response = await client.get("/api/admin/calls")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 4
        # Should NOT include rendered_prompt in the list view
        for item in body:
            assert "rendered_prompt" not in item
            assert "inputs" not in item
            assert "response" not in item

    async def test_filter_by_model(self, calls_client) -> None:
        client, _ = calls_client

        response = await client.get("/api/admin/calls", params={"model": "claude-opus-4-5"})

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["model"] == "claude-opus-4-5"

    async def test_filter_by_prompt_version_id(self, calls_client) -> None:
        client, seeds = calls_client
        pv2_id = str(seeds["pv2"].id)

        response = await client.get("/api/admin/calls", params={"prompt_version_id": pv2_id})

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["prompt_version_id"] == pv2_id

    async def test_null_cost_is_serialized_as_none(self, calls_client) -> None:
        client, seeds = calls_client
        pv2_id = str(seeds["pv2"].id)

        response = await client.get("/api/admin/calls", params={"prompt_version_id": pv2_id})

        assert response.status_code == 200
        assert response.json()[0]["cost_usd"] is None

    async def test_error_field_present_when_set(self, calls_client) -> None:
        client, seeds = calls_client

        response = await client.get(
            "/api/admin/calls",
            params={"model": "claude-3-haiku-20240307"},
        )

        assert response.status_code == 200
        error_calls = [c for c in response.json() if c["error"] == "timeout"]
        assert len(error_calls) == 1


# ---------------------------------------------------------------------------
# Tests: GET /api/admin/calls/cost
# ---------------------------------------------------------------------------


class TestCostDashboard:
    async def test_returns_by_day_and_totals(self, calls_client) -> None:
        client, _ = calls_client

        response = await client.get("/api/admin/calls/cost")

        assert response.status_code == 200
        body = response.json()
        assert "by_day" in body
        assert "totals" in body

    async def test_by_day_has_correct_structure(self, calls_client) -> None:
        client, _ = calls_client

        response = await client.get("/api/admin/calls/cost")

        body = response.json()
        assert len(body["by_day"]) >= 1
        day_entry = body["by_day"][0]
        assert "day" in day_entry
        assert "cost_usd" in day_entry
        assert "calls" in day_entry

    async def test_totals_correct_sum_and_counts(self, calls_client) -> None:
        client, _ = calls_client

        response = await client.get("/api/admin/calls/cost")

        totals = response.json()["totals"]
        # 0.001 + 0.010 + 0.001 + 0 (NULL treated as 0)
        assert abs(totals["total_cost"] - 0.012) < 1e-4
        assert totals["total_calls"] == 4

    async def test_totals_error_rate_correct(self, calls_client) -> None:
        client, _ = calls_client

        response = await client.get("/api/admin/calls/cost")

        totals = response.json()["totals"]
        # 1 error out of 4 calls
        assert abs(totals["error_rate"] - 0.25) < 1e-6

    async def test_totals_avg_latency_excludes_nulls(self, calls_client) -> None:
        client, _ = calls_client

        response = await client.get("/api/admin/calls/cost")

        totals = response.json()["totals"]
        # latency_ms: 1000, 2000, 500, NULL → avg of 3 values = 1166.67
        assert totals["avg_latency_ms"] is not None
        assert abs(totals["avg_latency_ms"] - (1000 + 2000 + 500) / 3) < 1.0

    async def test_null_cost_does_not_crash(self, calls_client) -> None:
        """Ensure the cost endpoint handles NULL cost rows gracefully."""
        client, _ = calls_client
        # Just verifying it returns 200 with valid structure
        response = await client.get("/api/admin/calls/cost")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tests: GET /api/admin/calls/{call_id}
# ---------------------------------------------------------------------------


class TestGetCallDetail:
    async def test_detail_includes_rendered_prompt(self, calls_client) -> None:
        client, seeds = calls_client
        call_id = str(seeds["call_normal"].id)

        response = await client.get(f"/api/admin/calls/{call_id}")

        assert response.status_code == 200
        body = response.json()
        assert "rendered_prompt" in body
        assert body["rendered_prompt"] == "Write a cover letter for Backend Engineer."
        assert "inputs" in body
        assert "response" in body

    async def test_detail_contains_lean_fields_too(self, calls_client) -> None:
        client, seeds = calls_client
        call_id = str(seeds["call_normal"].id)

        response = await client.get(f"/api/admin/calls/{call_id}")

        body = response.json()
        assert body["model"] == "claude-3-haiku-20240307"
        assert body["cost_usd"] == pytest.approx(0.001, abs=1e-6)

    async def test_returns_404_for_unknown_id(self, calls_client) -> None:
        client, _ = calls_client
        unknown = str(uuid.uuid4())

        response = await client.get(f"/api/admin/calls/{unknown}")

        assert response.status_code == 404
