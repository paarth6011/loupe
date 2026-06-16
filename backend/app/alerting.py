from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.baselines import bucket_for, bucket_label
from app.config import Settings
from app.detection import seasonal_anomaly, zscore_anomaly
from app.models import Alert, BaselineProfile, MetricSample, Monitor


@dataclass
class _AnomalyEval:
    """A detector-agnostic anomaly verdict, so the latency/cost paths can format
    one message regardless of which detector produced it."""

    detector: str  # "seasonal" | "zscore"
    firing: bool
    z: float
    recent: float  # recent center (seasonal: median; zscore: mean)
    baseline_center: float
    baseline_spread: float
    baseline_n: int
    bucket: int | None  # the hour bucket (seasonal only; None for zscore)


def _evaluate_anomaly(
    full_values: list[float],
    profile: BaselineProfile | None,
    z_threshold: float,
    settings: Settings,
) -> _AnomalyEval | None:
    """Judge a metric's recent window, seasonal baseline first then rolling z.

    Prefers the current hour's seasonal baseline when it's populated enough to
    trust (``anomaly_bucket_min_samples``); otherwise falls back to the
    rolling-window z-score over ``full_values``. Returns ``None`` when neither
    can judge (no recent data / no spread / not enough history) so the rule
    simply doesn't fire.
    """
    recent_values = full_values[: settings.anomaly_recent_samples]
    if (
        settings.anomaly_seasonal_enabled
        and profile is not None
        and profile.n >= settings.anomaly_bucket_min_samples
    ):
        seasonal = seasonal_anomaly(
            recent_values,
            baseline_center=profile.center,
            baseline_scale=profile.scale,
            baseline_n=profile.n,
            z_threshold=z_threshold,
        )
        if seasonal is not None:
            return _AnomalyEval(
                "seasonal",
                seasonal.firing,
                seasonal.z,
                seasonal.recent_center,
                seasonal.baseline_center,
                seasonal.baseline_scale,
                seasonal.baseline_n,
                profile.bucket,
            )
    rolling = zscore_anomaly(
        full_values,
        recent_samples=settings.anomaly_recent_samples,
        min_baseline=settings.anomaly_min_baseline,
        z_threshold=z_threshold,
    )
    if rolling is None:
        return None
    return _AnomalyEval(
        "zscore",
        rolling.firing,
        rolling.z,
        rolling.recent_mean,
        rolling.baseline_mean,
        rolling.baseline_std,
        rolling.baseline_n,
        None,
    )


def _open_alerts_by_rule(db: Session, workload_id: int) -> dict[str, Alert]:
    """All currently-open alerts for a workload, keyed by rule. Fetched once per
    ingest so the per-rule reconcile below needs no further queries (the DB-level
    unique index still guards against a concurrent open)."""
    rows = db.scalars(
        select(Alert).where(
            Alert.workload_id == workload_id,
            Alert.resolved_at.is_(None),
        )
    ).all()
    return {a.rule: a for a in rows}


def _reconcile(
    db: Session,
    open_by_rule: dict[str, Alert],
    account_id: int,
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
    existing = open_by_rule.get(rule)
    if firing and existing is None:
        alert = Alert(
            account_id=account_id,
            workload_id=workload_id,
            rule=rule,
            message=message,
            severity=severity,
            detector=detector,
        )
        # A concurrent ingest may open the same alert between our read and this
        # insert; the partial unique index rejects the duplicate. Do the add+flush
        # inside a savepoint so its rollback both discards our duplicate and
        # leaves the surrounding ingest transaction usable.
        try:
            with db.begin_nested():
                db.add(alert)
                db.flush()
        except IntegrityError:
            return  # another ingest opened it first — nothing to do
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

    # One window fetch serves both the threshold rules (which look at the most
    # recent `error_rate_window` samples) and the anomaly detectors (which need
    # `anomaly_recent + anomaly_baseline` of history). Pull the larger span once,
    # newest-first, and slice the threshold window off the front.
    history_n = max(
        settings.error_rate_window,
        settings.anomaly_recent_samples + settings.anomaly_baseline_window,
    )
    history = db.scalars(
        select(MetricSample)
        .where(MetricSample.workload_id == sample.workload_id)
        .order_by(MetricSample.ts.desc(), MetricSample.id.desc())
        .limit(history_n)
    ).all()
    recent = history[: settings.error_rate_window]
    # The detectors must see only their own window: if error_rate_window is the
    # larger span, the extra rows would inflate the anomaly baseline beyond
    # anomaly_baseline_window. Slice the detector input back to its configured size.
    anomaly_history = history[
        : settings.anomaly_recent_samples + settings.anomaly_baseline_window
    ]

    # All open alerts for this workload, fetched once and reused by every
    # _reconcile call below (replacing one SELECT per rule).
    open_by_rule = _open_alerts_by_rule(db, sample.workload_id)

    # Per-workload monitor overrides. Absent a row, a rule is enabled at its
    # global default threshold. Disabling a rule makes its firing False below,
    # which resolves any of its currently-open alerts on this ingest.
    monitors = {
        m.rule: m
        for m in db.scalars(
            select(Monitor).where(Monitor.workload_id == sample.workload_id)
        ).all()
    }

    def cfg(rule: str, default: float) -> tuple[bool, float]:
        m = monitors.get(rule)
        if m is None:
            return True, default
        return m.enabled, (m.threshold if m.threshold is not None else default)

    # Rule: high_latency — firing while any sample in the recent window is over
    # the threshold; resolves once the breach ages out of the window.
    lat_enabled, lat_threshold = cfg("high_latency", settings.latency_threshold_ms)
    max_latency = max((s.latency_ms for s in recent), default=0)
    latency_severity = "critical" if max_latency >= 3 * lat_threshold else "warning"
    _reconcile(
        db,
        open_by_rule,
        sample.account_id,
        sample.workload_id,
        "high_latency",
        lat_enabled and max_latency > lat_threshold,
        f"latency {max_latency}ms exceeded threshold {lat_threshold:.0f}ms",
        latency_severity,
        opened,
        resolved,
    )

    # Rule: high_error_rate — firing while the recent error fraction is at/above
    # the threshold (needs a minimum sample count); resolves when it drops back.
    err_enabled, err_threshold = cfg("high_error_rate", settings.error_rate_threshold)
    error_firing = False
    error_message = ""
    error_severity = "warning"
    if len(recent) >= settings.error_rate_min_samples:
        errors = sum(1 for s in recent if s.status == "error")
        rate = errors / len(recent)
        error_firing = err_enabled and rate >= err_threshold
        error_severity = "critical" if rate >= 0.8 else "warning"
        error_message = (
            f"error rate {rate:.0%} over last {len(recent)} samples "
            f"exceeded {err_threshold:.0%}"
        )
    _reconcile(
        db,
        open_by_rule,
        sample.account_id,
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
    cost_enabled, cost_threshold = cfg(
        "cost_spike", settings.cost_per_request_threshold_usd
    )
    costs = [s.cost_usd for s in recent if s.cost_usd is not None]
    max_cost = max(costs, default=0.0)
    cost_severity = "critical" if max_cost >= 3 * cost_threshold else "warning"
    cost_message = (
        f"a request cost ${max_cost:.4f}, over the "
        f"${cost_threshold:.2f} per-call ceiling"
    )
    _reconcile(
        db,
        open_by_rule,
        sample.account_id,
        sample.workload_id,
        "cost_spike",
        cost_enabled and max_cost > cost_threshold,
        cost_message,
        cost_severity,
        opened,
        resolved,
    )

    # Rule: token_spike — a single call burning more tokens (in+out) than the
    # ceiling.
    tok_enabled, tok_threshold = cfg(
        "token_spike", settings.token_per_request_threshold
    )
    token_totals = [
        (s.input_tokens or 0) + (s.output_tokens or 0)
        for s in recent
        if s.input_tokens is not None or s.output_tokens is not None
    ]
    max_tokens = max(token_totals, default=0)
    token_severity = "critical" if max_tokens >= 3 * tok_threshold else "warning"
    token_message = (
        f"a request used {max_tokens:,} tokens, over the "
        f"{tok_threshold:,.0f} per-call ceiling"
    )
    _reconcile(
        db,
        open_by_rule,
        sample.account_id,
        sample.workload_id,
        "token_spike",
        tok_enabled and max_tokens > tok_threshold,
        token_message,
        token_severity,
        opened,
        resolved,
    )

    # Rule: rate_limit_surge — provider 429s clustering in the recent window.
    rl_enabled, rl_threshold = cfg("rate_limit_surge", settings.rate_limit_threshold)
    rl_firing = False
    rl_message = ""
    rl_severity = "warning"
    if len(recent) >= settings.rate_limit_min_samples:
        rate_limited = sum(1 for s in recent if s.error_type == "rate_limit")
        frac = rate_limited / len(recent)
        rl_firing = rl_enabled and frac >= rl_threshold
        rl_severity = "critical" if frac >= 0.5 else "warning"
        rl_message = (
            f"{frac:.0%} of the last {len(recent)} calls were rate-limited "
            f"(over the {rl_threshold:.0%} threshold)"
        )
    _reconcile(
        db,
        open_by_rule,
        sample.account_id,
        sample.workload_id,
        "rate_limit_surge",
        rl_firing,
        rl_message,
        rl_severity,
        opened,
        resolved,
    )

    # --- Statistical anomaly detection --------------------------------------
    # Learn each workload's own baseline and flag when recent calls deviate from
    # it — catches "slow/expensive for THIS workload", which fixed thresholds
    # miss. Prefers a seasonal (per hour-of-day) baseline so a predictably-slow
    # hour isn't a false alarm, and falls back to the rolling-window z-score over
    # the `anomaly_history` span fetched above when a bucket isn't populated yet.

    def _severity_for(z: float, z_threshold: float) -> str:
        return "critical" if z >= 1.5 * z_threshold else "warning"

    # The current hour's seasonal baselines for this workload (latency + cost),
    # if any have been learned. One small keyed lookup; absent rows -> fallback.
    seasonal_profiles: dict[str, BaselineProfile] = {}
    if settings.anomaly_seasonal_enabled:
        current_bucket = bucket_for(sample.ts)
        seasonal_profiles = {
            p.metric: p
            for p in db.scalars(
                select(BaselineProfile).where(
                    BaselineProfile.workload_id == sample.workload_id,
                    BaselineProfile.bucket == current_bucket,
                )
            ).all()
        }

    # Rule: latency_anomaly — recent latency abnormally high vs the baseline.
    lat_anom_enabled, lat_z = cfg("latency_anomaly", settings.anomaly_z_threshold)
    lat = _evaluate_anomaly(
        [float(s.latency_ms) for s in anomaly_history],
        seasonal_profiles.get("latency"),
        lat_z,
        settings,
    )
    lat_message = ""
    lat_severity = "warning"
    lat_detector = "zscore"
    if lat is not None:
        lat_severity = _severity_for(lat.z, lat_z)
        lat_detector = lat.detector
        if lat.detector == "seasonal":
            lat_message = (
                f"latency median {lat.recent:.0f}ms over the last "
                f"{settings.anomaly_recent_samples} calls — {lat.z:.1f}σ above this "
                f"workload's typical {bucket_label(lat.bucket)} baseline "
                f"{lat.baseline_center:.0f}ms ± {lat.baseline_spread:.0f}ms "
                f"({lat.baseline_n} samples)"
            )
        else:
            lat_message = (
                f"latency averaged {lat.recent:.0f}ms over the last "
                f"{settings.anomaly_recent_samples} calls — {lat.z:.1f}σ above this "
                f"workload's baseline {lat.baseline_center:.0f}ms "
                f"± {lat.baseline_spread:.0f}ms ({lat.baseline_n} samples)"
            )
    _reconcile(
        db,
        open_by_rule,
        sample.account_id,
        sample.workload_id,
        "latency_anomaly",
        lat_anom_enabled and lat is not None and lat.firing,
        lat_message,
        lat_severity,
        opened,
        resolved,
        detector=lat_detector,
    )

    # Rule: cost_anomaly — recent per-call cost abnormally high vs the baseline.
    # Dormant for HTTP workloads (no cost samples -> detector abstains).
    cost_anom_enabled, cost_z = cfg("cost_anomaly", settings.anomaly_z_threshold)
    cost = _evaluate_anomaly(
        [float(s.cost_usd) for s in anomaly_history if s.cost_usd is not None],
        seasonal_profiles.get("cost"),
        cost_z,
        settings,
    )
    cost_message = ""
    cost_severity = "warning"
    cost_detector = "zscore"
    if cost is not None:
        cost_severity = _severity_for(cost.z, cost_z)
        cost_detector = cost.detector
        if cost.detector == "seasonal":
            cost_message = (
                f"cost median ${cost.recent:.4f}/call over the last "
                f"{settings.anomaly_recent_samples} calls — {cost.z:.1f}σ above this "
                f"workload's typical {bucket_label(cost.bucket)} baseline "
                f"${cost.baseline_center:.4f} ± ${cost.baseline_spread:.4f} "
                f"({cost.baseline_n} samples)"
            )
        else:
            cost_message = (
                f"cost averaged ${cost.recent:.4f}/call over the last "
                f"{settings.anomaly_recent_samples} calls — {cost.z:.1f}σ above this "
                f"workload's baseline ${cost.baseline_center:.4f} "
                f"± ${cost.baseline_spread:.4f} ({cost.baseline_n} samples)"
            )
    _reconcile(
        db,
        open_by_rule,
        sample.account_id,
        sample.workload_id,
        "cost_anomaly",
        cost_anom_enabled and cost is not None and cost.firing,
        cost_message,
        cost_severity,
        opened,
        resolved,
        detector=cost_detector,
    )

    return opened, resolved
