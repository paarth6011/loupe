"""Per-model pricing (USD per 1M tokens) for cost estimation.

These are approximate list prices — a static table you should edit to match
current provider pricing. It's used to compute `cost_usd` from token counts when
a client doesn't supply an explicit cost.
"""

import re

# Providers echo back the dated snapshot they actually served (e.g.
# "claude-haiku-4-5-20251001"), but the table is keyed by the stable alias. Strip
# a trailing "-YYYYMMDD" so snapshots resolve to their family's price without
# having to add a new key every time a snapshot ships.
_DATE_SUFFIX = re.compile(r"-\d{8}$")

# model -> (input_usd_per_1m, output_usd_per_1m)
PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    # OpenAI (approximate)
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
}


def compute_cost(
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    """Estimate cost in USD from model + token counts, or None if the model is
    unknown (so we never invent a number we can't justify)."""
    if not model:
        return None
    # Try the exact id first, then fall back to the alias with any dated
    # snapshot suffix removed.
    price = PRICING.get(model) or PRICING.get(_DATE_SUFFIX.sub("", model))
    if price is None:
        return None
    in_rate, out_rate = price
    used_in = input_tokens or 0
    used_out = output_tokens or 0
    return round(used_in / 1_000_000 * in_rate + used_out / 1_000_000 * out_rate, 6)
