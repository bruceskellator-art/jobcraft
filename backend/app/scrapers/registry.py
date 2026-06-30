"""Curated registry of tech companies with SG presence whose public job boards
we scrape via Greenhouse or Lever.

Each token here was verified against the live public APIs (HTTP 200 + live jobs):
- Greenhouse:  https://boards-api.greenhouse.io/v1/boards/{token}/jobs
- Lever:       https://api.lever.co/v0/postings/{slug}?mode=json

Greenhouse/Lever have no keyword-search API — they expose one company's board at a
time, addressed by a fixed token/slug. So the scrape UI lets users pick companies by
NAME; this module maps the chosen name to the verified board token.

To extend: add a CompanyBoard with a token you have verified returns 200 + jobs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompanyBoard:
    """A curated company whose Greenhouse or Lever board we can scrape."""

    name: str  # display name; the key the UI sends (matched case-insensitively)
    greenhouse: str | None = None  # greenhouse board token, or None
    lever: str | None = None  # lever company slug, or None
    sg_presence: bool = True  # has a meaningful Singapore hiring presence


# Verified 2026-06-26. 57 Greenhouse + 8 Lever = 65 companies.
CURATED_COMPANIES: tuple[CompanyBoard, ...] = (
    CompanyBoard("Stripe", greenhouse="stripe"),
    CompanyBoard("Anthropic", greenhouse="anthropic"),
    CompanyBoard("Databricks", greenhouse="databricks"),
    CompanyBoard("Datadog", greenhouse="datadog"),
    CompanyBoard("Figma", greenhouse="figma"),
    CompanyBoard("GitLab", greenhouse="gitlab"),
    CompanyBoard("Twilio", greenhouse="twilio"),
    CompanyBoard("Cloudflare", greenhouse="cloudflare"),
    CompanyBoard("MongoDB", greenhouse="mongodb"),
    CompanyBoard("Elastic", greenhouse="elastic"),
    CompanyBoard("Airtable", greenhouse="airtable", sg_presence=False),
    CompanyBoard("Coinbase", greenhouse="coinbase"),
    CompanyBoard("Brex", greenhouse="brex", sg_presence=False),
    CompanyBoard("Scale AI", greenhouse="scaleai"),
    CompanyBoard("Discord", greenhouse="discord", sg_presence=False),
    CompanyBoard("Reddit", greenhouse="reddit"),
    CompanyBoard("Pinterest", greenhouse="pinterest"),
    CompanyBoard("Robinhood", greenhouse="robinhood", sg_presence=False),
    CompanyBoard("Affirm", greenhouse="affirm", sg_presence=False),
    CompanyBoard("Instacart", greenhouse="instacart", sg_presence=False),
    CompanyBoard("Lyft", greenhouse="lyft", sg_presence=False),
    CompanyBoard("Asana", greenhouse="asana"),
    CompanyBoard("Dropbox", greenhouse="dropbox", sg_presence=False),
    CompanyBoard("Okta", greenhouse="okta"),
    CompanyBoard("Block (Square)", greenhouse="block"),
    CompanyBoard("DoorDash", greenhouse="doordashusa", sg_presence=False),
    CompanyBoard("Box", greenhouse="boxinc"),
    CompanyBoard("Thunes", greenhouse="thunes"),
    CompanyBoard("Cialfo", greenhouse="cialfo"),
    CompanyBoard("GovTech (Open Government Products)", greenhouse="govtech"),
    CompanyBoard("Sumo Logic", greenhouse="sumologic"),
    CompanyBoard("Samsara", greenhouse="samsara"),
    CompanyBoard("Gusto", greenhouse="gusto", sg_presence=False),
    CompanyBoard("Chime", greenhouse="chime", sg_presence=False),
    CompanyBoard("Nubank", greenhouse="nubank", sg_presence=False),
    CompanyBoard("GoCardless", greenhouse="gocardless"),
    CompanyBoard("Airbnb", greenhouse="airbnb"),
    CompanyBoard("Roblox", greenhouse="roblox", sg_presence=False),
    CompanyBoard("Twitch", greenhouse="twitch"),
    CompanyBoard("Mixpanel", greenhouse="mixpanel"),
    CompanyBoard("Amplitude", greenhouse="amplitude"),
    CompanyBoard("Vercel", greenhouse="vercel", sg_presence=False),
    CompanyBoard("Netlify", greenhouse="netlify", sg_presence=False),
    CompanyBoard("PlanetScale", greenhouse="planetscale", sg_presence=False),
    CompanyBoard("Cockroach Labs", greenhouse="cockroachlabs"),
    CompanyBoard("Postman", greenhouse="postman"),
    CompanyBoard("Algolia", greenhouse="algolia"),
    CompanyBoard("Gemini", greenhouse="gemini"),
    CompanyBoard("BitGo", greenhouse="bitgo"),
    CompanyBoard("Fireblocks", greenhouse="fireblocks"),
    CompanyBoard("ConsenSys", greenhouse="consensys"),
    CompanyBoard("Blockchain.com", greenhouse="blockchain"),
    CompanyBoard("Bybit", greenhouse="bybit"),
    CompanyBoard("OKX", greenhouse="okx"),
    CompanyBoard("Remote", greenhouse="remote"),
    CompanyBoard("Grafana Labs", greenhouse="grafanalabs"),
    CompanyBoard("Temporal Technologies", greenhouse="temporaltechnologies"),
    # Lever boards
    CompanyBoard("Ninja Van", lever="ninjavan"),
    CompanyBoard("Nium", lever="nium"),
    CompanyBoard("PatSnap", lever="patsnap"),
    CompanyBoard("Binance", lever="binance"),
    CompanyBoard("Crypto.com", lever="crypto"),
    CompanyBoard("Anyscale", lever="anyscale", sg_presence=False),
    CompanyBoard("Ledger", lever="ledger"),
    CompanyBoard("Toku", lever="toku"),
)


# Precomputed once at import: curated names sorted for stable UI ordering.
_COMPANY_NAMES: tuple[str, ...] = tuple(sorted(c.name for c in CURATED_COMPANIES))


def company_names() -> list[str]:
    """Return curated company display names, sorted for stable UI ordering."""
    return list(_COMPANY_NAMES)


def lookup(name: str) -> CompanyBoard | None:
    """Return the CompanyBoard for *name* (case-insensitive), or None."""
    low = name.strip().lower()
    return next((c for c in CURATED_COMPANIES if c.name.lower() == low), None)
