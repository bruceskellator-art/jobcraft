from __future__ import annotations

import hashlib

from app.scrapers.types import RawJobPosting

_HASH_ENCODING = "utf-8"


def content_hash(raw: RawJobPosting) -> str:
    """Return a hex SHA-256 of company + title + raw_content (lowercased, stripped)."""
    blob = "\n".join([
        raw.company.strip().lower(),
        raw.title.strip().lower(),
        raw.raw_content.strip().lower(),
    ])
    return hashlib.sha256(blob.encode(_HASH_ENCODING)).hexdigest()


def dedup_key(raw: RawJobPosting) -> tuple[str, str]:
    """Return the preferred deduplication key: (source, source_id) or (source, content_hash)."""
    if raw.source_id is not None:
        return (raw.source, raw.source_id)
    return (raw.source, content_hash(raw))
