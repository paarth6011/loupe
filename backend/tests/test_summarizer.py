from app.models import Alert, Workload
from app.summarizer import (
    AlertContext,
    TemplateSummarizer,
    generate_and_store_summary,
)


def _ctx(**overrides) -> AlertContext:
    base = dict(
        workload_name="gpt-4o-chat",
        rule="high_latency",
        severity="critical",
        message="latency 5000ms exceeded threshold 1000ms",
        sample_count=20,
        error_rate=0.05,
        p95_ms=3200.0,
    )
    base.update(overrides)
    return AlertContext(**base)


def test_template_summarizer_mentions_workload_and_rule():
    out = TemplateSummarizer().summarize(_ctx())
    assert "gpt-4o-chat" in out
    assert "high_latency" in out
    assert "CRITICAL" in out


def test_ingest_populates_alert_summary(client, auth_headers):
    """Happy path: an opened alert gets a summary written by the background task."""
    resp = client.post(
        "/metrics",
        json={"workload": "sum-wl", "latency_ms": 5000, "status": "ok"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    # The response body was serialized before the background task ran.
    assert resp.json()["triggered_alerts"][0]["summary"] is None
    workload_id = resp.json()["sample"]["workload_id"]

    alerts = client.get(
        f"/alerts?workload_id={workload_id}", headers=auth_headers
    ).json()
    assert alerts[0]["summary"] == "[summary] sum-wl/high_latency"


def test_generate_summary_swallows_summarizer_errors(db_session):
    """Failure path: a summarizer error leaves Alert.summary NULL, no raise."""
    workload = Workload(name="boom-wl")
    db_session.add(workload)
    db_session.commit()
    alert = Alert(
        workload_id=workload.id,
        rule="high_latency",
        message="m",
        severity="warning",
    )
    db_session.add(alert)
    db_session.commit()

    class Boom:
        def summarize(self, ctx: AlertContext) -> str:
            raise RuntimeError("model unavailable")

    # Must not raise; summarizer fails before any DB session is opened.
    generate_and_store_summary(alert.id, _ctx(), Boom(), lambda: db_session)

    db_session.refresh(alert)
    assert alert.summary is None
