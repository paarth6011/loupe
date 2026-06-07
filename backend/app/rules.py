"""The catalogue of alert rules.

One source of truth shared by the alerting engine and the monitors API/UI: what
rules exist, what their tunable threshold means, and where the global default
comes from. A per-workload ``Monitor`` row can override the threshold or disable
a rule entirely; absent one, the global default (from env/Settings) applies.
"""

from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True)
class RuleSpec:
    rule: str
    label: str
    unit: str  # human unit for the threshold value (ms, USD, fraction, σ, …)
    settings_attr: str  # attribute on Settings holding the global default
    detector: str  # "threshold" | "zscore"
    integer: bool  # whether the threshold is a whole number (for display)


RULE_SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "high_latency", "High latency", "ms", "latency_threshold_ms", "threshold", True
    ),
    RuleSpec(
        "high_error_rate",
        "High error rate",
        "fraction",
        "error_rate_threshold",
        "threshold",
        False,
    ),
    RuleSpec(
        "cost_spike",
        "Cost spike (per call)",
        "USD",
        "cost_per_request_threshold_usd",
        "threshold",
        False,
    ),
    RuleSpec(
        "token_spike",
        "Token spike (per call)",
        "tokens",
        "token_per_request_threshold",
        "threshold",
        True,
    ),
    RuleSpec(
        "rate_limit_surge",
        "Rate-limit surge",
        "fraction",
        "rate_limit_threshold",
        "threshold",
        False,
    ),
    RuleSpec(
        "latency_anomaly",
        "Latency anomaly",
        "σ",
        "anomaly_z_threshold",
        "zscore",
        False,
    ),
    RuleSpec(
        "cost_anomaly", "Cost anomaly", "σ", "anomaly_z_threshold", "zscore", False
    ),
)

RULE_SPEC_BY_NAME: dict[str, RuleSpec] = {s.rule: s for s in RULE_SPECS}


def default_threshold(spec: RuleSpec, settings: Settings) -> float:
    """The global default threshold for a rule, read from Settings."""
    return float(getattr(settings, spec.settings_attr))
