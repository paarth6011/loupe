from app.pricing import compute_cost


def test_compute_cost_known_model():
    # Haiku 4.5: $1/1M input, $5/1M output.
    assert compute_cost("claude-haiku-4-5", 1_000_000, 1_000_000) == 6.0
    assert compute_cost("claude-haiku-4-5", 420, 85) == round(
        420 / 1_000_000 * 1.0 + 85 / 1_000_000 * 5.0, 6
    )


def test_compute_cost_unknown_or_missing():
    assert compute_cost("not-a-real-model", 100, 100) is None
    assert compute_cost(None, 100, 100) is None
    # Known model with no tokens -> $0, not None.
    assert compute_cost("gpt-4o", None, None) == 0.0
