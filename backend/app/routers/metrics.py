from datetime import datetime, timezone
from math import ceil

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.aggregation import as_utc, parse_window, percentile
from app.alerting import evaluate_thresholds
from app.cache import Cache, get_cache
from app.config import Settings, get_settings
from app.database import get_db, get_session_factory
from app.deps import get_current_user
from app.models import MetricSample, Workload
from app.notifications import AlertEvent, Notifier, get_notifier
from app.pricing import compute_cost
from app.schemas.auth import CurrentUser
from app.schemas.metrics import (
    CostByModel,
    CostByWorkload,
    CostSummary,
    MetricIngest,
    MetricIngestResponse,
    MetricsSummary,
    MetricsTimeseries,
    TimeseriesPoint,
)
from app.summarizer import (
    AlertContext,
    Summarizer,
    generate_and_store_summary,
    get_summarizer,
)

MAX_BUCKETS = 500

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
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    summarizer: Summarizer = Depends(get_summarizer),
    notifier: Notifier = Depends(get_notifier),
    session_factory: sessionmaker = Depends(get_session_factory),
    _: CurrentUser = Depends(get_current_user),
) -> MetricIngestResponse:
    workload = _get_or_create_workload(db, body.workload)

    # Use the client-supplied cost, else estimate it from model + token counts.
    cost_usd = body.cost_usd
    if cost_usd is None:
        cost_usd = compute_cost(body.model, body.input_tokens, body.output_tokens)

    sample = MetricSample(
        workload_id=workload.id,
        latency_ms=body.latency_ms,
        status=body.status,
        tokens=body.tokens,
        model=body.model,
        provider=body.provider,
        input_tokens=body.input_tokens,
        output_tokens=body.output_tokens,
        cost_usd=cost_usd,
        operation=body.operation,
        error_type=body.error_type,
    )
    if body.ts is not None:
        sample.ts = body.ts
    db.add(sample)
    db.flush()  # assign id + server-default ts and make it visible to threshold queries

    opened, resolved = evaluate_thresholds(db, sample, settings)
    # Capture what the background tasks need before commit expires the ORM objects.
    opened_info = [(a.id, a.rule, a.severity, a.message) for a in opened]
    resolved_info = [(a.id, a.rule, a.severity, a.message) for a in resolved]
    workload_name = workload.name
    workload_id = workload.id

    db.commit()
    db.refresh(sample)

    # Push alert notifications off the request path (open + resolve).
    for alert_id, rule, severity, message in opened_info:
        background_tasks.add_task(
            notifier.notify,
            AlertEvent("firing", alert_id, workload_name, rule, severity, message),
        )
    for alert_id, rule, severity, message in resolved_info:
        background_tasks.add_task(
            notifier.notify,
            AlertEvent("resolved", alert_id, workload_name, rule, severity, message),
        )

    # Generate LLM summaries off the request path; ingestion never blocks on it.
    if opened_info:
        recent = db.scalars(
            select(MetricSample)
            .where(MetricSample.workload_id == workload_id)
            .order_by(MetricSample.ts.desc(), MetricSample.id.desc())
            .limit(settings.error_rate_window)
        ).all()
        count = len(recent)
        errors = sum(1 for s in recent if s.status == "error")
        latencies = [s.latency_ms for s in recent]
        for alert_id, rule, severity, message in opened_info:
            ctx = AlertContext(
                workload_name=workload_name,
                rule=rule,
                severity=severity,
                message=message,
                sample_count=count,
                error_rate=round(errors / count, 4) if count else 0.0,
                p95_ms=percentile(latencies, 95),
            )
            background_tasks.add_task(
                generate_and_store_summary,
                alert_id,
                ctx,
                summarizer,
                session_factory,
            )

    return MetricIngestResponse(
        sample=sample, triggered_alerts=opened, resolved_alerts=resolved
    )


@router.get("/metrics/summary", response_model=MetricsSummary)
def metrics_summary(
    workload_id: int,
    window: str = "1h",
    db: Session = Depends(get_db),
    cache: Cache = Depends(get_cache),
    settings: Settings = Depends(get_settings),
    _: CurrentUser = Depends(get_current_user),
) -> MetricsSummary:
    try:
        delta = parse_window(window)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    cache_key = f"summary:{workload_id}:{window}"
    cached = cache.get(cache_key)
    if cached is not None:
        return MetricsSummary.model_validate_json(cached)

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

    summary = MetricsSummary(
        workload_id=workload_id,
        window=window,
        request_count=count,
        error_count=errors,
        error_rate=round(errors / count, 4) if count else 0.0,
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
        total_input_tokens=sum(s.input_tokens or 0 for s in in_window),
        total_output_tokens=sum(s.output_tokens or 0 for s in in_window),
        total_cost_usd=round(sum(s.cost_usd or 0.0 for s in in_window), 6),
    )
    cache.set(cache_key, summary.model_dump_json(), settings.summary_cache_ttl_seconds)
    return summary


@router.get("/metrics/timeseries", response_model=MetricsTimeseries)
def metrics_timeseries(
    workload_id: int,
    window: str = "1h",
    bucket: str = "5m",
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> MetricsTimeseries:
    try:
        window_delta = parse_window(window)
        bucket_delta = parse_window(bucket)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    if bucket_delta > window_delta:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bucket must be <= window",
        )

    n_buckets = ceil(window_delta / bucket_delta)
    if n_buckets > MAX_BUCKETS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"too many buckets ({n_buckets}); widen the bucket size",
        )

    if db.get(Workload, workload_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="workload not found"
        )

    now = datetime.now(timezone.utc)
    start = now - window_delta
    samples = db.scalars(
        select(MetricSample).where(MetricSample.workload_id == workload_id)
    ).all()

    grouped: list[list[MetricSample]] = [[] for _ in range(n_buckets)]
    for s in samples:
        ts = as_utc(s.ts)
        if ts < start or ts > now:
            continue
        idx = int((ts - start) / bucket_delta)
        idx = min(idx, n_buckets - 1)  # clamp the right edge
        grouped[idx].append(s)

    points: list[TimeseriesPoint] = []
    for i, group in enumerate(grouped):
        count = len(group)
        errors = sum(1 for s in group if s.status == "error")
        latencies = [s.latency_ms for s in group]
        points.append(
            TimeseriesPoint(
                bucket_start=start + bucket_delta * i,
                request_count=count,
                error_rate=round(errors / count, 4) if count else 0.0,
                latency_p50_ms=percentile(latencies, 50),
                latency_p95_ms=percentile(latencies, 95),
                input_tokens=sum(s.input_tokens or 0 for s in group),
                output_tokens=sum(s.output_tokens or 0 for s in group),
                cost_usd=round(sum(s.cost_usd or 0.0 for s in group), 6),
            )
        )

    return MetricsTimeseries(
        workload_id=workload_id, window=window, bucket=bucket, points=points
    )


@router.get("/metrics/cost", response_model=CostSummary)
def metrics_cost(
    window: str = "24h",
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> CostSummary:
    """Account-wide spend over a window, broken down by model and by workload."""
    try:
        delta = parse_window(window)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    since = datetime.now(timezone.utc) - delta
    samples = db.scalars(select(MetricSample)).all()
    in_window = [s for s in samples if as_utc(s.ts) >= since]
    names = {w.id: w.name for w in db.scalars(select(Workload)).all()}

    by_model: dict[tuple[str, str | None], dict] = {}
    by_workload: dict[int, dict] = {}
    total_in = total_out = 0
    total_cost = 0.0

    for s in in_window:
        it, ot, cost = s.input_tokens or 0, s.output_tokens or 0, s.cost_usd or 0.0
        total_in += it
        total_out += ot
        total_cost += cost

        wl = by_workload.setdefault(s.workload_id, {"requests": 0, "cost": 0.0})
        wl["requests"] += 1
        wl["cost"] += cost

        if s.model:
            key = (s.model, s.provider)
            md = by_model.setdefault(
                key, {"requests": 0, "in": 0, "out": 0, "cost": 0.0}
            )
            md["requests"] += 1
            md["in"] += it
            md["out"] += ot
            md["cost"] += cost

    models = [
        CostByModel(
            model=m,
            provider=p,
            requests=v["requests"],
            input_tokens=v["in"],
            output_tokens=v["out"],
            cost_usd=round(v["cost"], 6),
        )
        for (m, p), v in by_model.items()
    ]
    models.sort(key=lambda x: x.cost_usd, reverse=True)

    workloads = [
        CostByWorkload(
            workload_id=wid,
            workload=names.get(wid, f"#{wid}"),
            requests=v["requests"],
            cost_usd=round(v["cost"], 6),
        )
        for wid, v in by_workload.items()
    ]
    workloads.sort(key=lambda x: x.cost_usd, reverse=True)

    return CostSummary(
        window=window,
        total_requests=len(in_window),
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_cost_usd=round(total_cost, 6),
        by_model=models,
        by_workload=workloads,
    )
