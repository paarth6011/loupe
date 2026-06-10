"""The DB-level invariant: at most one *unresolved* alert per (workload, rule),
and the reconcile path tolerates losing the race to a concurrent ingest."""

import pytest
from sqlalchemy.exc import IntegrityError

from app import alerting
from app.models import Alert, Workload


def _wl(db, name="dedup-wl"):
    wl = Workload(name=name)
    db.add(wl)
    db.flush()
    return wl


def _open_alert(workload_id, rule="high_latency", message="m"):
    return Alert(
        workload_id=workload_id, rule=rule, message=message, severity="warning"
    )


def test_partial_unique_index_blocks_duplicate_open_alerts(db_session):
    wl = _wl(db_session)
    db_session.add(_open_alert(wl.id))
    db_session.commit()

    db_session.add(_open_alert(wl.id, message="dup"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_resolved_alert_does_not_block_a_new_one(db_session):
    wl = _wl(db_session)
    first = _open_alert(wl.id)
    db_session.add(first)
    db_session.flush()
    # Resolve it, then a brand-new open alert for the same (workload, rule) is OK.
    from datetime import datetime, timezone

    first.resolved_at = datetime.now(timezone.utc)
    db_session.add(_open_alert(wl.id, message="second"))
    db_session.commit()  # must not raise

    open_count = (
        db_session.query(Alert)
        .filter(Alert.workload_id == wl.id, Alert.resolved_at.is_(None))
        .count()
    )
    assert open_count == 1


def test_reconcile_tolerates_lost_race(db_session):
    """If a concurrent ingest opened the alert first (so our insert collides),
    _reconcile drops the duplicate without raising or recording it as opened."""
    wl = _wl(db_session)
    db_session.add(_open_alert(wl.id))  # the "winner"
    # flush (not commit) keeps the ingest-style transaction active, exactly as in
    # production where the sample is flushed before reconcile runs.
    db_session.flush()

    # An empty open-by-rule snapshot simulates our read missing the alert a
    # concurrent ingest just opened, so the INSERT collides with the unique index.
    opened: list = []
    resolved: list = []
    alerting._reconcile(
        db_session,
        {},
        wl.id,
        "high_latency",
        True,
        "racing",
        "warning",
        opened,
        resolved,
    )

    assert opened == []  # duplicate dropped, no exception
    open_count = (
        db_session.query(Alert)
        .filter(Alert.workload_id == wl.id, Alert.resolved_at.is_(None))
        .count()
    )
    assert open_count == 1  # still exactly one
