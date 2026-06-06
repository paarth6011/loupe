import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Alert, MetricSample, Workload


def test_create_workload_and_sample(db_session):
    """Happy path: a workload with a metric sample persists with defaults."""
    workload = Workload(name="gpt-sim-1")
    db_session.add(workload)
    db_session.commit()

    assert workload.id is not None
    assert workload.created_at is not None

    sample = MetricSample(
        workload_id=workload.id, latency_ms=120, status="ok", tokens=42
    )
    db_session.add(sample)
    db_session.commit()

    assert sample.id is not None
    assert sample.ts is not None  # server_default applied
    assert workload.samples[0].id == sample.id


def test_alert_starts_unresolved(db_session):
    workload = Workload(name="gpt-sim-2")
    db_session.add(workload)
    db_session.commit()

    alert = Alert(workload_id=workload.id, rule="latency_p95", message="high latency")
    db_session.add(alert)
    db_session.commit()

    assert alert.triggered_at is not None
    assert alert.resolved_at is None


def test_metric_sample_requires_status(db_session):
    """Failure path: status is NOT NULL, so commit must raise."""
    workload = Workload(name="gpt-sim-3")
    db_session.add(workload)
    db_session.commit()

    db_session.add(MetricSample(workload_id=workload.id, latency_ms=10))  # no status
    with pytest.raises(IntegrityError):
        db_session.commit()
