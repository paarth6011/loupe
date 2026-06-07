from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Alert, MetricSample


def _open_alert(db: Session, workload_id: int, rule: str) -> Alert | None:
    return db.scalars(
        select(Alert).where(
            Alert.workload_id == workload_id,
            Alert.rule == rule,
            Alert.resolved_at.is_(None),
        )
    ).first()


def _reconcile(
    db: Session,
    workload_id: int,
    rule: str,
    firing: bool,
    message: str,
    severity: str,
    opened: list[Alert],
    resolved: list[Alert],
) -> None:
    """Open an alert when a rule starts firing; resolve it when it recovers.

    Dedup falls out naturally: at most one unresolved alert exists per
    (workload, rule), so a sustained breach does not create duplicates.
    """
    existing = _open_alert(db, workload_id, rule)
    if firing and existing is None:
        alert = Alert(
            workload_id=workload_id, rule=rule, message=message, severity=severity
        )
        db.add(alert)
        db.flush()
        opened.append(alert)
    elif not firing and existing is not None:
        existing.resolved_at = datetime.now(timezone.utc)
        db.flush()
        resolved.append(existing)


def evaluate_thresholds(
    db: Session, sample: MetricSample, settings: Settings
) -> tuple[list[Alert], list[Alert]]:
    """Evaluate threshold rules over the recent window for a workload.

    Returns (opened, resolved) alerts. Firing state is computed from the
    most-recent window of samples so alerts both raise and clear on their own.
    """
    opened: list[Alert] = []
    resolved: list[Alert] = []

    recent = db.scalars(
        select(MetricSample)
        .where(MetricSample.workload_id == sample.workload_id)
        .order_by(MetricSample.ts.desc(), MetricSample.id.desc())
        .limit(settings.error_rate_window)
    ).all()

    # Rule: high_latency — firing while any sample in the recent window is over
    # the threshold; resolves once the breach ages out of the window.
    max_latency = max((s.latency_ms for s in recent), default=0)
    latency_severity = (
        "critical" if max_latency >= 3 * settings.latency_threshold_ms else "warning"
    )
    _reconcile(
        db,
        sample.workload_id,
        "high_latency",
        max_latency > settings.latency_threshold_ms,
        f"latency {max_latency}ms exceeded threshold {settings.latency_threshold_ms}ms",
        latency_severity,
        opened,
        resolved,
    )

    # Rule: high_error_rate — firing while the recent error fraction is at/above
    # the threshold (needs a minimum sample count); resolves when it drops back.
    error_firing = False
    error_message = ""
    error_severity = "warning"
    if len(recent) >= settings.error_rate_min_samples:
        errors = sum(1 for s in recent if s.status == "error")
        rate = errors / len(recent)
        error_firing = rate >= settings.error_rate_threshold
        error_severity = "critical" if rate >= 0.8 else "warning"
        error_message = (
            f"error rate {rate:.0%} over last {len(recent)} samples "
            f"exceeded {settings.error_rate_threshold:.0%}"
        )
    _reconcile(
        db,
        sample.workload_id,
        "high_error_rate",
        error_firing,
        error_message,
        error_severity,
        opened,
        resolved,
    )

    # --- LLM-tuned rules ----------------------------------------------------
    # These read the LLM-specific fields and are naturally dormant for HTTP
    # workloads, where cost_usd / tokens / error_type are null: max(...) falls
    # back to 0 and the rate-limit fraction is 0, so they never fire.

    # Rule: cost_spike — a single call costing more than the per-request ceiling
    # (catches runaway max_tokens or an exploded context window).
    costs = [s.cost_usd for s in recent if s.cost_usd is not None]
    max_cost = max(costs, default=0.0)
    cost_severity = (
        "critical"
        if max_cost >= 3 * settings.cost_per_request_threshold_usd
        else "warning"
    )
    cost_message = (
        f"a request cost ${max_cost:.4f}, over the "
        f"${settings.cost_per_request_threshold_usd:.2f} per-call ceiling"
    )
    _reconcile(
        db,
        sample.workload_id,
        "cost_spike",
        max_cost > settings.cost_per_request_threshold_usd,
        cost_message,
        cost_severity,
        opened,
        resolved,
    )

    # Rule: token_spike — a single call burning more tokens (in+out) than the
    # ceiling; an explainable stand-in until per-workload baselines (step 7).
    token_totals = [
        (s.input_tokens or 0) + (s.output_tokens or 0)
        for s in recent
        if s.input_tokens is not None or s.output_tokens is not None
    ]
    max_tokens = max(token_totals, default=0)
    token_severity = (
        "critical"
        if max_tokens >= 3 * settings.token_per_request_threshold
        else "warning"
    )
    token_message = (
        f"a request used {max_tokens:,} tokens, over the "
        f"{settings.token_per_request_threshold:,} per-call ceiling"
    )
    _reconcile(
        db,
        sample.workload_id,
        "token_spike",
        max_tokens > settings.token_per_request_threshold,
        token_message,
        token_severity,
        opened,
        resolved,
    )

    # Rule: rate_limit_surge — provider 429s clustering in the recent window.
    rl_firing = False
    rl_message = ""
    rl_severity = "warning"
    if len(recent) >= settings.rate_limit_min_samples:
        rate_limited = sum(1 for s in recent if s.error_type == "rate_limit")
        frac = rate_limited / len(recent)
        rl_firing = frac >= settings.rate_limit_threshold
        rl_severity = "critical" if frac >= 0.5 else "warning"
        rl_message = (
            f"{frac:.0%} of the last {len(recent)} calls were rate-limited "
            f"(over the {settings.rate_limit_threshold:.0%} threshold)"
        )
    _reconcile(
        db,
        sample.workload_id,
        "rate_limit_surge",
        rl_firing,
        rl_message,
        rl_severity,
        opened,
        resolved,
    )

    return opened, resolved
