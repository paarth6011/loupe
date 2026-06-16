"""Seasonal (time-of-day) baselines for the anomaly detectors.

A workload with a daily rhythm — busy and slow at 9am, quiet overnight — defeats
a plain rolling-window z-score: a narrow window false-positives every morning,
and a window wide enough to smooth the cycle reacts slowly and hides real
spikes. The fix is to compare like-with-like — 9am against *this workload's
typical 9am*.

This module precomputes that "typical": a robust baseline (median + MAD) per
(workload, metric, UTC hour-of-day) from recent history, refreshed on a cadence
by a background worker (mirroring retention.py). The detector then looks up the
current hour's baseline at ingest; when a bucket is too sparse to trust it
abstains and the rolling-window z-score takes over (see alerting.py).

UTC hour-of-day is deliberate: a daily cycle recurs at a fixed UTC offset, so no
per-tenant timezone config is needed (a DST shift only blurs by an hour). Day of
week is a future refinement — 168 weekly buckets need ~7× the history to fill.
"""

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.aggregation import as_utc, window_start
from app.config import Settings
from app.database import set_current_account
from app.detection import mad_scale
from app.models import Account, BaselineProfile, MetricSample

logger = logging.getLogger("uvicorn.error")


def bucket_for(ts: datetime) -> int:
    """The seasonal bucket a timestamp falls in: its UTC hour-of-day (0–23)."""
    return as_utc(ts).hour


def bucket_label(bucket: int) -> str:
    """Human label for a bucket, e.g. 9 -> ``09:00`` (UTC), for alert messages."""
    return f"{bucket:02d}:00"


@dataclass
class RefreshResult:
    accounts: int  # tenants scanned
    profiles_written: int  # (workload, metric, bucket) rows recomputed


def _sample_values(latency_ms: int, cost_usd: float | None) -> dict[str, float]:
    """The per-metric values a sample contributes (omitting absent ones)."""
    values = {"latency": float(latency_ms)}
    if cost_usd is not None:
        values["cost"] = float(cost_usd)
    return values


def _refresh_account(db: Session, account_id: int, settings: Settings) -> int:
    """Recompute every seasonal baseline for one (already-pinned) tenant.

    Full recompute from the trailing window, then a delete-and-insert swap — the
    rows are disposable derived state, so this is simpler and more portable than
    a per-row upsert (and avoids dialect-specific ON CONFLICT in the test DB).
    """
    cutoff = window_start(
        db.bind.dialect.name, timedelta(days=7 * settings.anomaly_baseline_weeks)
    )
    # Explicit account_id filter (not only the RLS pin): in single-tenant self-host
    # the app serves as the owner role where RLS is bypassed, so the filter is what
    # keeps the scan scoped. Under the restricted role the pin and filter agree.
    rows = db.execute(
        select(
            MetricSample.workload_id,
            MetricSample.ts,
            MetricSample.latency_ms,
            MetricSample.cost_usd,
        ).where(
            MetricSample.account_id == account_id,
            MetricSample.ts >= cutoff,
        )
    ).all()

    # Bucket the values: (workload_id, metric, hour) -> [values].
    grouped: dict[tuple[int, str, int], list[float]] = defaultdict(list)
    for workload_id, ts, latency_ms, cost_usd in rows:
        bucket = bucket_for(ts)
        for metric, value in _sample_values(latency_ms, cost_usd).items():
            grouped[(workload_id, metric, bucket)].append(value)

    db.execute(delete(BaselineProfile).where(BaselineProfile.account_id == account_id))

    written = 0
    min_samples = settings.anomaly_bucket_min_samples
    for (workload_id, metric, bucket), values in grouped.items():
        if len(values) < min_samples:
            continue  # too sparse to trust — the detector will fall back instead
        center = median(values)
        scale = mad_scale(values, center)
        db.add(
            BaselineProfile(
                account_id=account_id,
                workload_id=workload_id,
                metric=metric,
                bucket=bucket,
                center=center,
                scale=scale,
                n=len(values),
            )
        )
        written += 1
    return written


def refresh_baselines(
    session_factory: sessionmaker, settings: Settings
) -> RefreshResult:
    """Recompute seasonal baselines for every tenant. Safe to call on demand.

    Pins each account in turn so it works under row-level security too: the
    restricted runtime role sees a tenant's samples only once pinned, and the
    WITH CHECK policy lets it write that tenant's baseline rows. (Contrast with
    retention, which never pins and so no-ops under RLS.)
    """
    if not settings.anomaly_seasonal_enabled or settings.anomaly_baseline_weeks <= 0:
        return RefreshResult(0, 0)

    # accounts is an auth-bootstrap table (not under RLS), so the worker can
    # enumerate tenants without a pin.
    with session_factory() as db:
        account_ids = list(db.scalars(select(Account.id)).all())

    written = 0
    for account_id in account_ids:
        with session_factory() as db:
            set_current_account(db, account_id)
            try:
                written += _refresh_account(db, account_id, settings)
                db.commit()
            except Exception:  # one tenant's failure must not abort the rest
                db.rollback()
                logger.exception("baseline refresh failed for account %d", account_id)
    return RefreshResult(accounts=len(account_ids), profiles_written=written)


def start_baseline_worker(session_factory: sessionmaker, settings: Settings) -> None:
    """Spawn a daemon thread that refreshes seasonal baselines on a cadence.

    No-op when the seasonal path is disabled. The detector degrades gracefully
    until the first sweep populates the table (it falls back to the rolling
    z-score), so an initial delay before the first run is harmless.
    """
    if not settings.anomaly_seasonal_enabled or settings.anomaly_baseline_weeks <= 0:
        return

    def _loop() -> None:
        interval = max(settings.anomaly_baseline_refresh_hours, 1) * 3600
        while True:
            try:
                result = refresh_baselines(session_factory, settings)
                logger.info(
                    "baselines: refreshed %d profiles across %d accounts",
                    result.profiles_written,
                    result.accounts,
                )
            except Exception:  # never let the sweeper crash the process
                logger.exception("baseline refresh sweep failed")
            time.sleep(interval)

    threading.Thread(target=_loop, name="baselines", daemon=True).start()
    logger.info(
        "baseline worker started: %dw history, every %dh",
        settings.anomaly_baseline_weeks,
        settings.anomaly_baseline_refresh_hours,
    )
