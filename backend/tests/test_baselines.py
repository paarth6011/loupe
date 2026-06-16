"""Seasonal baseline refresh + the detector's seasonal path (see baselines.py).

These run at the DB level (not via the API) so timestamps — which decide the
hour bucket — can be controlled precisely. Times are anchored to real `now()`
because the refresh window is relative to wall-clock; subtracting whole days
keeps the same UTC hour, so the learned bucket matches the trigger's bucket.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import sessionmaker

from app.alerting import evaluate_thresholds
from app.baselines import bucket_for, refresh_baselines
from app.config import get_settings
from app.models import BaselineProfile, MetricSample, Workload


def _session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False)


def _workload(db, account_id, name="seasonal-wl"):
    wl = Workload(account_id=account_id, name=name)
    db.add(wl)
    db.commit()
    db.refresh(wl)
    return wl


def _sample(db, account_id, workload_id, ts, latency, cost=None):
    s = MetricSample(
        account_id=account_id,
        workload_id=workload_id,
        ts=ts,
        latency_ms=latency,
        status="ok",
        cost_usd=cost,
    )
    db.add(s)
    return s


def _fill_bucket(db, account_id, workload_id, slot, n=24, base=200, cost=None):
    """Seed `n` varied samples inside a single hour `slot` (so the bucket has
    spread, otherwise MAD is 0 and the detector abstains)."""
    for i in range(n):
        _sample(
            db,
            account_id,
            workload_id,
            slot + timedelta(seconds=i),
            base + (i % 11),
            cost=None if cost is None else cost + (i % 11) * 0.001,
        )
    db.commit()


def test_bucket_for_is_utc_hour():
    assert bucket_for(datetime(2026, 6, 16, 9, 30)) == 9
    assert bucket_for(datetime(2026, 6, 16, 0, 5)) == 0
    assert bucket_for(datetime(2026, 6, 16, 23, 59, tzinfo=timezone.utc)) == 23


def test_refresh_learns_per_hour_baseline(db_engine, db_session, account_id):
    wl = _workload(db_session, account_id)
    slot = (datetime.now(timezone.utc) - timedelta(days=2)).replace(
        minute=0, second=0, microsecond=0
    )
    _fill_bucket(db_session, account_id, wl.id, slot, n=24, base=200)

    result = refresh_baselines(_session_factory(db_engine), get_settings())

    assert result.accounts >= 1
    assert result.profiles_written == 1  # one (workload, latency, hour) bucket
    prof = (
        db_session.query(BaselineProfile)
        .filter_by(workload_id=wl.id, metric="latency", bucket=slot.hour)
        .one()
    )
    assert prof.n == 24
    assert 200 <= prof.center <= 211
    assert prof.scale > 0  # has spread, so the detector can use it


def test_refresh_skips_sparse_buckets(db_engine, db_session, account_id):
    wl = _workload(db_session, account_id)
    slot = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        minute=0, second=0, microsecond=0
    )
    # Below anomaly_bucket_min_samples (20): too sparse to trust.
    _fill_bucket(db_session, account_id, wl.id, slot, n=10, base=200)

    result = refresh_baselines(_session_factory(db_engine), get_settings())

    assert result.profiles_written == 0
    assert db_session.query(BaselineProfile).count() == 0


def test_seasonal_anomaly_fires_against_its_own_bucket(
    db_engine, db_session, account_id
):
    wl = _workload(db_session, account_id)
    now = datetime.now(timezone.utc)
    # Learn a ~200ms baseline for this hour, two days back (same UTC hour as now).
    learn_slot = (now - timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
    _fill_bucket(db_session, account_id, wl.id, learn_slot, n=24, base=200)
    refresh_baselines(_session_factory(db_engine), get_settings())

    # Five recent calls at ~600ms in the same hour bucket today — well above this
    # workload's typical value for the hour, but still under the 1000ms absolute
    # threshold, so only the statistical detector can catch it.
    trigger_slot = now.replace(minute=0, second=0, microsecond=0)
    recent = [
        _sample(db_session, account_id, wl.id, trigger_slot + timedelta(seconds=i), 600)
        for i in range(5)
    ]
    db_session.commit()

    opened, _ = evaluate_thresholds(db_session, recent[-1], get_settings())
    by_rule = {a.rule: a for a in opened}

    assert "latency_anomaly" in by_rule
    alert = by_rule["latency_anomaly"]
    assert alert.detector == "seasonal"
    assert "typical" in alert.message and "σ" in alert.message
    assert "high_latency" not in by_rule  # under the absolute ceiling


def test_seasonal_no_alarm_for_predictably_slow_hour(db_engine, db_session, account_id):
    """The core fix: a value that is *normal for this hour* raises no alarm,
    where a flat baseline drawn from quieter hours would have false-positived."""
    wl = _workload(db_session, account_id)
    now = datetime.now(timezone.utc)
    learn_slot = (now - timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
    _fill_bucket(db_session, account_id, wl.id, learn_slot, n=24, base=200)
    refresh_baselines(_session_factory(db_engine), get_settings())

    # Recent calls ~210ms: a touch above the 200ms center but well within the
    # bucket's normal spread, so not an anomaly.
    trigger_slot = now.replace(minute=0, second=0, microsecond=0)
    recent = [
        _sample(db_session, account_id, wl.id, trigger_slot + timedelta(seconds=i), 210)
        for i in range(5)
    ]
    db_session.commit()

    opened, _ = evaluate_thresholds(db_session, recent[-1], get_settings())
    assert "latency_anomaly" not in {a.rule for a in opened}


def test_refresh_baselines_endpoint_requires_admin(client):
    assert client.post("/admin/refresh-baselines").status_code == 401


def test_refresh_baselines_endpoint(client, auth_headers):
    resp = client.post("/admin/refresh-baselines", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "accounts" in body and "profiles_written" in body
