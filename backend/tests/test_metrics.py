def _post_metric(client, headers, **overrides):
    body = {"workload": "gpt-sim-1", "latency_ms": 100, "status": "ok"}
    body.update(overrides)
    return client.post("/metrics", json=body, headers=headers)


def test_ingest_creates_sample_and_workload(client, auth_headers):
    """Happy path: a normal sample is stored, workload auto-created, no alerts."""
    resp = _post_metric(client, auth_headers, latency_ms=120, tokens=42)
    assert resp.status_code == 201
    body = resp.json()
    assert body["sample"]["id"] is not None
    assert body["sample"]["workload_id"] is not None
    assert body["sample"]["latency_ms"] == 120
    assert body["sample"]["tokens"] == 42
    assert body["triggered_alerts"] == []


def test_high_latency_triggers_alert(client, auth_headers):
    resp = _post_metric(client, auth_headers, latency_ms=5000)
    assert resp.status_code == 201
    alerts = resp.json()["triggered_alerts"]
    assert len(alerts) == 1
    assert alerts[0]["rule"] == "high_latency"


def test_high_latency_alert_is_deduped(client, auth_headers):
    first = _post_metric(client, auth_headers, latency_ms=5000)
    assert len(first.json()["triggered_alerts"]) == 1
    # Second breach while the first alert is still open -> no new alert.
    second = _post_metric(client, auth_headers, latency_ms=6000)
    assert second.json()["triggered_alerts"] == []


def test_high_error_rate_triggers_alert(client, auth_headers):
    rules_seen = set()
    for _ in range(5):  # error_rate_min_samples=5, threshold=0.5 -> 100% errors
        resp = _post_metric(client, auth_headers, status="error", latency_ms=50)
        for a in resp.json()["triggered_alerts"]:
            rules_seen.add(a["rule"])
    assert "high_error_rate" in rules_seen


def test_high_latency_alert_auto_resolves(client, auth_headers):
    """A latency spike opens an alert; normal samples then resolve it."""
    from app.config import Settings, get_settings
    from app.main import app

    # Small recent window so the spike ages out after a few normal samples.
    app.dependency_overrides[get_settings] = lambda: Settings(
        error_rate_window=3, error_rate_min_samples=3, latency_threshold_ms=1000
    )
    try:
        spike = _post_metric(client, auth_headers, latency_ms=5000)
        assert any(
            a["rule"] == "high_latency" for a in spike.json()["triggered_alerts"]
        )

        last = None
        for _ in range(3):  # push the spike out of the size-3 window
            last = _post_metric(client, auth_headers, latency_ms=50)
        assert any(a["rule"] == "high_latency" for a in last.json()["resolved_alerts"])

        resolved = client.get("/alerts?resolved=true", headers=auth_headers).json()
        assert any(a["rule"] == "high_latency" for a in resolved)
        open_alerts = client.get("/alerts?resolved=false", headers=auth_headers).json()
        assert all(a["rule"] != "high_latency" for a in open_alerts)
    finally:
        del app.dependency_overrides[get_settings]


def test_ingest_requires_auth(client):
    resp = _post_metric(client, {})  # no auth header
    assert resp.status_code == 401


def test_ingest_rejects_invalid_status(client, auth_headers):
    """Failure path: status outside the allowed literal is a 422."""
    resp = _post_metric(client, auth_headers, status="weird")
    assert resp.status_code == 422
