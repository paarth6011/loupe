"""Public status-page model: derive each published workload's health from its
recent samples and open alerts. The logic is deliberately simple and
explainable — an open critical alert is an outage, an open warning is a
degradation, a workload that has stopped reporting is "unknown", and everything
else is operational."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.aggregation import percentile, window_start
from app.models import Alert, MetricSample, Workload

# A workload that hasn't reported within this window is treated as "unknown"
# rather than operational — we genuinely can't vouch for it.
STALE_AFTER = timedelta(minutes=10)
UPTIME_WINDOW = timedelta(hours=24)
LATENCY_WINDOW = timedelta(hours=1)

# Severity ranking for "worst open alert" and for rolling components up into the
# overall headline.
_RANK = {"operational": 0, "unknown": 1, "degraded": 2, "down": 3}


@dataclass
class StatusComponent:
    name: str
    status: str  # operational | degraded | down | unknown
    uptime_24h: float | None  # percent of last-24h samples that were ok
    latency_p50_ms: float | None  # median latency over the last hour
    last_sample_at: datetime | None


@dataclass
class StatusPage:
    overall: str
    generated_at: datetime
    components: list[StatusComponent]


def _component(db: Session, workload: Workload) -> StatusComponent:
    dialect = db.bind.dialect.name

    last_sample_at = db.scalar(
        select(func.max(MetricSample.ts)).where(
            MetricSample.workload_id == workload.id
        )
    )

    # Uptime over the last 24h: share of samples that were "ok".
    total, ok = db.execute(
        select(
            func.count(),
            func.coalesce(
                func.sum(case((MetricSample.status == "ok", 1), else_=0)), 0
            ),
        ).where(
            MetricSample.workload_id == workload.id,
            MetricSample.ts >= window_start(dialect, UPTIME_WINDOW),
        )
    ).one()
    uptime = round(100.0 * ok / total, 3) if total else None

    # Median latency over the last hour (bounded, low-traffic public endpoint).
    latencies = db.scalars(
        select(MetricSample.latency_ms).where(
            MetricSample.workload_id == workload.id,
            MetricSample.ts >= window_start(dialect, LATENCY_WINDOW),
        )
    ).all()
    p50 = percentile(list(latencies), 50) if latencies else None

    # Worst open alert decides degraded vs. down.
    open_severities = set(
        db.scalars(
            select(Alert.severity).where(
                Alert.workload_id == workload.id,
                Alert.resolved_at.is_(None),
            )
        ).all()
    )
    is_stale = (
        last_sample_at is None
        or last_sample_at < window_start(dialect, STALE_AFTER)
    )

    if "critical" in open_severities:
        status = "down"
    elif open_severities:
        status = "degraded"
    elif is_stale:
        status = "unknown"
    else:
        status = "operational"

    return StatusComponent(
        name=workload.name,
        status=status,
        uptime_24h=uptime,
        latency_p50_ms=p50,
        last_sample_at=last_sample_at,
    )


def build_status_page(db: Session, workloads: list[Workload]) -> StatusPage:
    components = [_component(db, w) for w in workloads]
    # Overall headline is the worst component (operational if nothing published).
    worst = max((c.status for c in components), key=lambda s: _RANK[s], default=None)
    if worst is None or worst == "operational":
        overall = "operational"
    elif worst == "down":
        overall = "down"
    else:
        # Both "degraded" and "unknown" roll up to a partial-degradation headline.
        overall = "degraded"
    return StatusPage(
        overall=overall,
        generated_at=datetime.now(timezone.utc),
        components=components,
    )
