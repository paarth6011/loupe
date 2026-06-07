from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.detection import zscore_anomaly
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
    detector: str = "threshold",
) -> None:
    """Open an alert when a rule starts firing; resolve it when it recovers.

    Dedup falls out naturally: at most one unresolved alert exists per
    (workload, rule), so a sustained breach does not create duplicates.
    """
    existing = _open_alert(db, workload_id, rule)
    if firing and existing is None:
        alert = Alert(
            workload_id=workload_id,
            rule=rule,
            message=message,
            severity=severity,
            detector=detector,
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

    # --- Statistical anomaly detection (zscore) -----------------------------
    # Learn each workload's own baseline and flag when recent calls deviate from
    # it — catches "slow/expensive for THIS workload", which fixed thresholds
    # miss. Needs more history than the threshold rules, so it fetches its own.
    history = db.scalars(
        select(MetricSample)
        .where(MetricSample.workload_id == sample.workload_id)
        .order_by(MetricSample.ts.desc(), MetricSample.id.desc())
        .limit(settings.anomaly_recent_samples + settings.anomaly_baseline_window)
    ).all()

    def _severity_for(z: float) -> str:
        return "critical" if z >= 1.5 * settings.anomaly_z_threshold else "warning"

    # Rule: latency_anomaly — recent latency abnormally high vs the baseline.
    lat = zscore_anomaly(
        [float(s.latency_ms) for s in history],
        recent_samples=settings.anomaly_recent_samples,
        min_baseline=settings.anomaly_min_baseline,
        z_threshold=settings.anomaly_z_threshold,
    )
    lat_message = ""
    lat_severity = "warning"
    if lat is not None:
        lat_severity = _severity_for(lat.z)
        lat_message = (
            f"latency averaged {lat.recent_mean:.0f}ms over the last "
            f"{settings.anomaly_recent_samples} calls — {lat.z:.1f}σ above this "
            f"workload's baseline {lat.baseline_mean:.0f}ms "
            f"± {lat.baseline_std:.0f}ms ({lat.baseline_n} samples)"
        )
    _reconcile(
        db,
        sample.workload_id,
        "latency_anomaly",
        lat is not None and lat.firing,
        lat_message,
        lat_severity,
        opened,
        resolved,
        detector="zscore",
    )

    # Rule: cost_anomaly — recent per-call cost abnormally high vs the baseline.
    # Dormant for HTTP workloads (no cost samples -> detector abstains).
    cost = zscore_anomaly(
        [float(s.cost_usd) for s in history if s.cost_usd is not None],
        recent_samples=settings.anomaly_recent_samples,
        min_baseline=settings.anomaly_min_baseline,
        z_threshold=settings.anomaly_z_threshold,
    )
    cost_message = ""
    cost_severity = "warning"
    if cost is not None:
        cost_severity = _severity_for(cost.z)
        cost_message = (
            f"cost averaged ${cost.recent_mean:.4f}/call over the last "
            f"{settings.anomaly_recent_samples} calls — {cost.z:.1f}σ above this "
            f"workload's baseline ${cost.baseline_mean:.4f} "
            f"± ${cost.baseline_std:.4f} ({cost.baseline_n} samples)"
        )
    _reconcile(
        db,
        sample.workload_id,
        "cost_anomaly",
        cost is not None and cost.firing,
        cost_message,
        cost_severity,
        opened,
        resolved,
        detector="zscore",
    )

    return opened, resolved
