from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aggregation import as_utc, parse_window, percentile
from app.alerting import evaluate_thresholds
from app.config import Settings, get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import MetricSample, Workload
from app.schemas.auth import CurrentUser
from app.schemas.metrics import (
    MetricIngest,
    MetricIngestResponse,
    MetricsSummary,
)

router = APIRouter(tags=["metrics"])


def _get_or_create_workload(db: Session, name: str) -> Workload:
    workload = db.scalars(select(Workload).where(Workload.name == name)).first()
    if workload is not None:
        return workload
    workload = Workload(name=name)
    db.add(workload)
    db.flush()
    return workload


@router.post(
    "/metrics", response_model=MetricIngestResponse, status_code=status.HTTP_201_CREATED
)
def ingest_metric(
    body: MetricIngest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: CurrentUser = Depends(get_current_user),
) -> MetricIngestResponse:
    workload = _get_or_create_workload(db, body.workload)

    sample = MetricSample(
        workload_id=workload.id,
        latency_ms=body.latency_ms,
        status=body.status,
        tokens=body.tokens,
    )
    if body.ts is not None:
        sample.ts = body.ts
    db.add(sample)
    db.flush()  # assign id + server-default ts and make it visible to threshold queries

    triggered = evaluate_thresholds(db, sample, settings)

    db.commit()
    db.refresh(sample)
    return MetricIngestResponse(sample=sample, triggered_alerts=triggered)


@router.get("/metrics/summary", response_model=MetricsSummary)
def metrics_summary(
    workload_id: int,
    window: str = "1h",
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> MetricsSummary:
    try:
        delta = parse_window(window)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    if db.get(Workload, workload_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="workload not found"
        )

    since = datetime.now(timezone.utc) - delta
    samples = db.scalars(
        select(MetricSample).where(MetricSample.workload_id == workload_id)
    ).all()
    # Filter in Python so the window comparison is tz-safe across SQLite/Postgres.
    in_window = [s for s in samples if as_utc(s.ts) >= since]

    count = len(in_window)
    errors = sum(1 for s in in_window if s.status == "error")
    latencies = [s.latency_ms for s in in_window]

    return MetricsSummary(
        workload_id=workload_id,
        window=window,
        request_count=count,
        error_count=errors,
        error_rate=round(errors / count, 4) if count else 0.0,
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
    )
