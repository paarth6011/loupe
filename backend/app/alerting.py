from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Alert, MetricSample


def _open_alert_if_absent(
    db: Session, workload_id: int, rule: str, message: str
) -> Alert | None:
    """Create an alert for (workload, rule) unless one is already unresolved.

    Dedup keeps an alert storm from producing many rows for the same condition.
    Returns the new Alert, or None if an open alert already exists.
    """
    existing = db.scalars(
        select(Alert).where(
            Alert.workload_id == workload_id,
            Alert.rule == rule,
            Alert.resolved_at.is_(None),
        )
    ).first()
    if existing is not None:
        return None

    alert = Alert(workload_id=workload_id, rule=rule, message=message)
    db.add(alert)
    db.flush()
    return alert


def evaluate_thresholds(
    db: Session, sample: MetricSample, settings: Settings
) -> list[Alert]:
    """Evaluate threshold rules for a just-inserted sample. Returns new alerts."""
    triggered: list[Alert] = []

    # Rule: high_latency — single sample over the latency threshold.
    if sample.latency_ms > settings.latency_threshold_ms:
        alert = _open_alert_if_absent(
            db,
            sample.workload_id,
            "high_latency",
            f"latency {sample.latency_ms}ms exceeded "
            f"threshold {settings.latency_threshold_ms}ms",
        )
        if alert is not None:
            triggered.append(alert)

    # Rule: high_error_rate — error fraction across the recent sample window.
    recent = db.scalars(
        select(MetricSample)
        .where(MetricSample.workload_id == sample.workload_id)
        .order_by(MetricSample.ts.desc(), MetricSample.id.desc())
        .limit(settings.error_rate_window)
    ).all()
    if len(recent) >= settings.error_rate_min_samples:
        errors = sum(1 for s in recent if s.status == "error")
        rate = errors / len(recent)
        if rate >= settings.error_rate_threshold:
            alert = _open_alert_if_absent(
                db,
                sample.workload_id,
                "high_error_rate",
                f"error rate {rate:.0%} over last {len(recent)} samples "
                f"exceeded {settings.error_rate_threshold:.0%}",
            )
            if alert is not None:
                triggered.append(alert)

    return triggered
