"""Tests for the curated company registry."""

from __future__ import annotations

from app.scrapers.registry import CURATED_COMPANIES, company_names, lookup


def test_company_names_are_sorted_and_unique() -> None:
    names = company_names()
    assert names == sorted(names)
    assert len(names) == len({n.lower() for n in names})


def test_company_names_covers_all_entries() -> None:
    assert len(company_names()) == len(CURATED_COMPANIES)


def test_lookup_is_case_insensitive_and_trims() -> None:
    entry = lookup("  stripe  ")
    assert entry is not None
    assert entry.name == "Stripe"
    assert entry.greenhouse == "stripe"


def test_lookup_returns_lever_slug() -> None:
    entry = lookup("Binance")
    assert entry is not None
    assert entry.lever == "binance"
    assert entry.greenhouse is None


def test_lookup_unknown_returns_none() -> None:
    assert lookup("Not A Real Company") is None
