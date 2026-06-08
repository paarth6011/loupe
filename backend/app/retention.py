"""Data retention: prune samples (and stale resolved alerts) past a cutoff.

Keeps the hot tables bounded for long-running deployments. Disabled by default
(`RETENTION_DAYS=0`); when enabled, a background sweep runs on a cadence and the
same routine is exposed via an admin endpoint for on-demand runs.
"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker

from app.aggregation import window_start
from app.models import Alert, MetricSample

logger = logging.getLogger("uvicorn.error")


@dataclass
class PruneResult:
    samples_deleted: int
    alerts_deleted: int


def prune_old_data(session_factory: sessionmaker, days: int) -> PruneResult:
    """Delete metric samples older than ``days``, plus resolved alerts whose
    resolution is older than the cutoff. Returns how many rows went."""
    if days <= 0:
        return PruneResult(0, 0)
    with session_factory() as db:
        cutoff = window_start(db.bind.dialect.name, timedelta(days=days))
        samples = db.execute(
            delete(MetricSample).where(MetricSample.ts < cutoff)
        ).rowcount
        alerts = db.execute(
            delete(Alert).where(
                Alert.resolved_at.is_not(None), Alert.resolved_at < cutoff
            )
        ).rowcount
        db.commit()
    return PruneResult(samples_deleted=samples or 0, alerts_deleted=alerts or 0)


def start_retention_worker(
    session_factory: sessionmaker, days: int, sweep_hours: int
) -> None:
    """Spawn a daemon thread that prunes on a cadence. No-op when disabled."""
    if days <= 0:
        return

    def _loop() -> None:
        interval = max(sweep_hours, 1) * 3600
        while True:
            try:
                result = prune_old_data(session_factory, days)
                if result.samples_deleted or result.alerts_deleted:
                    logger.info(
                        "retention: pruned %d samples, %d alerts (older than %dd)",
                        result.samples_deleted,
                        result.alerts_deleted,
                        days,
                    )
            except Exception:  # never let the sweeper crash the process
                logger.exception("retention sweep failed")
            time.sleep(interval)

    threading.Thread(target=_loop, name="retention", daemon=True).start()
    logger.info("retention worker started: %dd, every %dh", days, sweep_hours)


# Convenience for the time bound used in `prune_old_data`, so tests can assert it.
def cutoff_for(dialect_name: str, days: int) -> datetime:
    return window_start(dialect_name, timedelta(days=days))
