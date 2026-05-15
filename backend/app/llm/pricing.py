from __future__ import annotations

from decimal import Decimal

# Per-1M-token rates (input, output) in USD.
# Unknown models return None — callers must handle that case.
PRICE_TABLE: dict[str, tuple[Decimal, Decimal]] = {
    # Claude models
    "claude-3-5-sonnet-20241022": (Decimal("3.00"), Decimal("15.00")),
    "claude-3-5-haiku-20241022": (Decimal("0.80"), Decimal("4.00")),
    "claude-3-opus-20240229": (Decimal("15.00"), Decimal("75.00")),
    "claude-3-sonnet-20240229": (Decimal("3.00"), Decimal("15.00")),
    "claude-3-haiku-20240307": (Decimal("0.25"), Decimal("1.25")),
    # OpenAI models
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4-turbo": (Decimal("10.00"), Decimal("30.00")),
    "gpt-3.5-turbo": (Decimal("0.50"), Decimal("1.50")),
}

_MILLION = Decimal("1_000_000")


def estimate_cost(
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> Decimal | None:
    """Return estimated USD cost for a call, or None if model is unknown."""
    rates = PRICE_TABLE.get(model)
    if rates is None:
        return None
    if input_tokens is None and output_tokens is None:
        return None

    input_price, output_price = rates
    cost = (Decimal(input_tokens or 0) / _MILLION * input_price) + (
        Decimal(output_tokens or 0) / _MILLION * output_price
    )
    return cost
