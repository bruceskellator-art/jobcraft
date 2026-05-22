from __future__ import annotations

from app.scrapers.dedupe import content_hash, dedup_key
from app.scrapers.types import RawJobPosting


def _make_posting(
    company: str = "Acme",
    title: str = "Engineer",
    raw_content: str = "Build things.",
    source_id: str | None = "123",
    source: str = "greenhouse:acme",
) -> RawJobPosting:
    return RawJobPosting(
        source=source,
        source_url="https://example.com/jobs/123",
        source_id=source_id,
        company=company,
        title=title,
        location="Singapore",
        remote_policy=None,
        raw_content=raw_content,
    )


class TestContentHash:
    def test_same_content_produces_same_hash(self) -> None:
        p1 = _make_posting()
        p2 = _make_posting()
        assert content_hash(p1) == content_hash(p2)

    def test_different_title_produces_different_hash(self) -> None:
        p1 = _make_posting(title="Engineer")
        p2 = _make_posting(title="Designer")
        assert content_hash(p1) != content_hash(p2)

    def test_different_company_produces_different_hash(self) -> None:
        p1 = _make_posting(company="Acme")
        p2 = _make_posting(company="Globex")
        assert content_hash(p1) != content_hash(p2)

    def test_different_raw_content_produces_different_hash(self) -> None:
        p1 = _make_posting(raw_content="Build things.")
        p2 = _make_posting(raw_content="Design things.")
        assert content_hash(p1) != content_hash(p2)

    def test_case_insensitive(self) -> None:
        p1 = _make_posting(company="ACME", title="ENGINEER", raw_content="BUILD THINGS.")
        p2 = _make_posting(company="acme", title="engineer", raw_content="build things.")
        assert content_hash(p1) == content_hash(p2)

    def test_returns_hex_string(self) -> None:
        result = content_hash(_make_posting())
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex is always 64 chars


class TestDedupKey:
    def test_uses_source_id_when_present(self) -> None:
        p = _make_posting(source="greenhouse:acme", source_id="42")
        key = dedup_key(p)
        assert key == ("greenhouse:acme", "42")

    def test_falls_back_to_content_hash_when_no_source_id(self) -> None:
        p = _make_posting(source="greenhouse:acme", source_id=None)
        key = dedup_key(p)
        assert key[0] == "greenhouse:acme"
        assert key[1] == content_hash(p)

    def test_same_posting_same_key(self) -> None:
        p1 = _make_posting()
        p2 = _make_posting()
        assert dedup_key(p1) == dedup_key(p2)
