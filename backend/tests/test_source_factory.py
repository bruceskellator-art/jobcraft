"""Tests for the get_source_factory dependency (query + curated companies)."""

from __future__ import annotations

import pytest

from app.deps import get_source_factory


async def _close_all(sources) -> None:
    for src in sources:
        aclose = getattr(src, "aclose", None)
        if callable(aclose):
            await aclose()


@pytest.mark.asyncio
async def test_query_builds_mycareersfuture_and_linkedin() -> None:
    build = get_source_factory()
    sources = build("python engineer", [])
    try:
        names = sorted(s.name for s in sources)
        assert names == ["linkedin", "mycareersfuture"]
    finally:
        await _close_all(sources)


@pytest.mark.asyncio
async def test_known_company_builds_greenhouse_source() -> None:
    build = get_source_factory()
    sources = build("", ["Stripe"])
    try:
        assert [s.name for s in sources] == ["greenhouse:stripe"]
    finally:
        await _close_all(sources)


@pytest.mark.asyncio
async def test_known_company_builds_lever_source() -> None:
    build = get_source_factory()
    sources = build("", ["Binance"])
    try:
        assert [s.name for s in sources] == ["lever:binance"]
    finally:
        await _close_all(sources)


@pytest.mark.asyncio
async def test_unknown_company_is_skipped() -> None:
    build = get_source_factory()
    sources = build("", ["Definitely Not Real"])
    try:
        assert sources == []
    finally:
        await _close_all(sources)


@pytest.mark.asyncio
async def test_blank_query_adds_no_keyword_sources() -> None:
    build = get_source_factory()
    sources = build("   ", [])
    try:
        assert sources == []
    finally:
        await _close_all(sources)
