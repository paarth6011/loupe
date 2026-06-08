from datetime import datetime, timedelta, timezone

from app.models import Alert, MetricSample, Workload
from app.retention import prune_old_data


def _seed(session_factory, *, old_days: int, fresh: int, old: int):
    """Create a workload with `fresh` recent samples and `old` samples aged
    `old_days` back, plus one resolved-long-ago alert and one recent alert."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_factory() as db:
        wl = Workload(name="ret-wl")
        db.add(wl)
        db.flush()
        for _ in range(fresh):
            db.add(MetricSample(workload_id=wl.id, latency_ms=50, status="ok", ts=now))
        for _ in range(old):
            db.add(
                MetricSample(
                    workload_id=wl.id,
                    latency_ms=50,
                    status="ok",
                    ts=now - timedelta(days=old_days),
                )
            )
        db.add(
            Alert(
                workload_id=wl.id,
                rule="high_latency",
                message="m",
                severity="warning",
                triggered_at=now - timedelta(days=old_days),
                resolved_at=now - timedelta(days=old_days),
            )
        )
        db.add(
            Alert(
                workload_id=wl.id,
                rule="high_latency",
                message="m",
                severity="warning",
                triggered_at=now,
                resolved_at=None,
            )
        )
        db.commit()
        return wl.id


def test_prune_removes_only_old_rows(db_engine):
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    _seed(factory, old_days=30, fresh=3, old=4)

    result = prune_old_data(factory, days=7)
    assert result.samples_deleted == 4  # only the 30-day-old samples
    assert result.alerts_deleted == 1  # only the long-resolved alert

    with factory() as db:
        assert db.query(MetricSample).count() == 3
        # The active alert survives; the stale resolved one is gone.
        remaining = db.query(Alert).all()
        assert len(remaining) == 1
        assert remaining[0].resolved_at is None


def test_prune_disabled_is_noop(db_engine):
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    _seed(factory, old_days=30, fresh=2, old=2)
    result = prune_old_data(factory, days=0)
    assert result.samples_deleted == 0
    with factory() as db:
        assert db.query(MetricSample).count() == 4


def test_admin_prune_endpoint(client, auth_headers):
    # Ingest a sample (recent), then prune with a 1-day window: nothing removed.
    client.post(
        "/metrics",
        json={"workload": "prune-wl", "latency_ms": 50, "status": "ok"},
        headers=auth_headers,
    )
    out = client.post("/admin/prune?days=1", headers=auth_headers)
    assert out.status_code == 200
    body = out.json()
    assert body["days"] == 1
    assert body["samples_deleted"] == 0


def test_admin_prune_requires_auth(client):
    assert client.post("/admin/prune?days=1").status_code == 401
