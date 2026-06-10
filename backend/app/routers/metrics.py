from datetime import datetime, timezone
from math import ceil

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.aggregation import as_utc, parse_window, percentile, window_start
from app.alerting import evaluate_thresholds
from app.cache import Cache, get_cache
from app.config import Settings, get_settings
from app.database import get_db, get_session_factory
from app.deps import get_current_user, require_ingest_auth
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


def _latency_percentiles(
    db: Session, conditions: list
) -> tuple[float | None, float | None]:
    """p50/p95 of latency_ms under the given filter.

    Uses SQL ``percentile_cont`` on Postgres (continuous/linear-interpolated, so
    it matches our Python ``percentile``); falls back to fetching just the
    latency column and computing in Python on SQLite, which lacks that function.
    """
    if db.bind.dialect.name == "postgresql":
        row = db.execute(
            select(
                func.percentile_cont(0.5).within_group(MetricSample.latency_ms.asc()),
                func.percentile_cont(0.95).within_group(MetricSample.latency_ms.asc()),
            ).where(*conditions)
        ).one()
        return row[0], row[1]
    latencies = db.scalars(select(MetricSample.latency_ms).where(*conditions)).all()
    return percentile(list(latencies), 50), percentile(list(latencies), 95)


def _get_or_create_workload(db: Session, name: str, max_workloads: int) -> Workload:
    workload = db.scalars(select(Workload).where(Workload.name == name)).first()
    if workload is not None:
        return workload

    # Cap auto-created cardinality: any valid key can mint workloads by name, so
    # without a ceiling a misbehaving or abusive client could create unlimited
    # rows. 0 disables the cap. (Checked only on a genuinely new name, so the hot
    # path of existing workloads is unaffected.)
    if max_workloads > 0:
        count = db.scalar(select(func.count()).select_from(Workload)) or 0
        if count >= max_workloads:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"workload limit ({max_workloads}) reached",
            )

    # Two concurrent ingests for the same new name both miss the SELECT above and
    # race to INSERT; the unique constraint lets only one win. Do the insert in a
    # savepoint so the loser's IntegrityError rolls back just this statement
    # (leaving the ingest transaction usable) and we re-read the winner.
    workload = Workload(name=name)
    try:
        with db.begin_nested():
            db.add(workload)
            db.flush()
    except IntegrityError:
        workload = db.scalars(
            select(Workload).where(Workload.name == name)
        ).first()
        if workload is None:  # not the unique-name race — surface it
            raise
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
    _: None = Depends(require_ingest_auth),
) -> MetricIngestResponse:
    workload = _get_or_create_workload(db, body.workload, settings.max_workloads)

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

    start = window_start(db.bind.dialect.name, delta)
    conds = [MetricSample.workload_id == workload_id, MetricSample.ts >= start]

    # Counts, error count, and token/cost totals are computed in SQL so the whole
    # window never lands in Python.
    count, errors, total_in, total_out, total_cost = db.execute(
        select(
            func.count(),
            func.coalesce(
                func.sum(case((MetricSample.status == "error", 1), else_=0)), 0
            ),
            func.coalesce(func.sum(MetricSample.input_tokens), 0),
            func.coalesce(func.sum(MetricSample.output_tokens), 0),
            func.coalesce(func.sum(MetricSample.cost_usd), 0.0),
        ).where(*conds)
    ).one()
    p50, p95 = _latency_percentiles(db, conds)

    summary = MetricsSummary(
        workload_id=workload_id,
        window=window,
        request_count=count,
        error_count=errors,
        error_rate=round(errors / count, 4) if count else 0.0,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_cost_usd=round(total_cost, 6),
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
    # Pull only the columns we bucket, and only those inside the window, instead
    # of loading every sample row for the workload.
    rows = db.execute(
        select(
            MetricSample.ts,
            MetricSample.latency_ms,
            MetricSample.status,
            MetricSample.input_tokens,
            MetricSample.output_tokens,
            MetricSample.cost_usd,
        ).where(
            MetricSample.workload_id == workload_id,
            MetricSample.ts >= window_start(db.bind.dialect.name, window_delta),
        )
    ).all()

    grouped: list[list] = [[] for _ in range(n_buckets)]
    for r in rows:
        ts = as_utc(r.ts)
        if ts < start or ts > now:
            continue
        idx = int((ts - start) / bucket_delta)
        idx = min(idx, n_buckets - 1)  # clamp the right edge
        grouped[idx].append(r)

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

    start = window_start(db.bind.dialect.name, delta)
    in_win = MetricSample.ts >= start
    _in = func.coalesce(func.sum(MetricSample.input_tokens), 0)
    _out = func.coalesce(func.sum(MetricSample.output_tokens), 0)
    _cost = func.coalesce(func.sum(MetricSample.cost_usd), 0.0)

    # All rollups are computed by the database, so spend reporting scales with
    # the table instead of pulling every sample into the app.
    total_requests, total_in, total_out, total_cost = db.execute(
        select(func.count(), _in, _out, _cost).where(in_win)
    ).one()

    model_rows = db.execute(
        select(
            MetricSample.model, MetricSample.provider, func.count(), _in, _out, _cost
        )
        .where(in_win, MetricSample.model.is_not(None))
        .group_by(MetricSample.model, MetricSample.provider)
    ).all()
    models = [
        CostByModel(
            model=m,
            provider=p,
            requests=rq,
            input_tokens=it,
            output_tokens=ot,
            cost_usd=round(c, 6),
        )
        for m, p, rq, it, ot, c in model_rows
    ]
    models.sort(key=lambda x: x.cost_usd, reverse=True)

    workload_rows = db.execute(
        select(
            Workload.id,
            Workload.name,
            func.count(MetricSample.id),
            func.coalesce(func.sum(MetricSample.cost_usd), 0.0),
        )
        .join(MetricSample, MetricSample.workload_id == Workload.id)
        .where(in_win)
        .group_by(Workload.id, Workload.name)
    ).all()
    workloads = [
        CostByWorkload(
            workload_id=wid, workload=name, requests=rq, cost_usd=round(c, 6)
        )
        for wid, name, rq, c in workload_rows
    ]
    workloads.sort(key=lambda x: x.cost_usd, reverse=True)

    return CostSummary(
        window=window,
        total_requests=total_requests,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_cost_usd=round(total_cost, 6),
        by_model=models,
        by_workload=workloads,
    )
