def _ingest(client, headers, workload, latency=50, status="ok"):
    return client.post(
        "/metrics",
        json={"workload": workload, "latency_ms": latency, "status": status},
        headers=headers,
    )


def test_list_alerts_empty(client, auth_headers):
    resp = client.get("/alerts", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_alerts_after_high_latency(client, auth_headers):
    _ingest(client, auth_headers, "al-wl", latency=5000)  # triggers high_latency
    resp = client.get("/alerts", headers=auth_headers)
    body = resp.json()
    assert len(body) == 1
    assert body[0]["rule"] == "high_latency"
    assert body[0]["resolved_at"] is None
    # The summary is filled in asynchronously (fake summarizer in tests).
    assert body[0]["summary"] is not None


def test_high_latency_severity_scales_with_magnitude(client, auth_headers):
    # 1.5x threshold -> warning
    warn = _ingest(client, auth_headers, "sev-warn", latency=1500)
    assert warn.json()["triggered_alerts"][0]["severity"] == "warning"
    # 5x threshold -> critical
    crit = _ingest(client, auth_headers, "sev-crit", latency=5000)
    assert crit.json()["triggered_alerts"][0]["severity"] == "critical"


def test_alerts_filter_by_workload(client, auth_headers):
    first = _ingest(client, auth_headers, "al-wl-1", latency=5000)
    workload_id = first.json()["sample"]["workload_id"]
    _ingest(client, auth_headers, "al-wl-2", latency=5000)

    resp = client.get(f"/alerts?workload_id={workload_id}", headers=auth_headers)
    body = resp.json()
    assert len(body) == 1
    assert body[0]["workload_id"] == workload_id


def test_alerts_filter_resolved_flag(client, auth_headers):
    _ingest(client, auth_headers, "al-wl", latency=5000)
    assert len(client.get("/alerts?resolved=false", headers=auth_headers).json()) == 1
    # Nothing resolves alerts in the MVP, so resolved=true is empty.
    assert client.get("/alerts?resolved=true", headers=auth_headers).json() == []


def test_list_alerts_requires_auth(client):
    assert client.get("/alerts").status_code == 401


# --- LLM-tuned rules --------------------------------------------------------


def _ingest_llm(client, headers, workload, **fields):
    body = {"workload": workload, "latency_ms": 50, "status": "ok"}
    body.update(fields)
    return client.post("/metrics", json=body, headers=headers)


def test_cost_spike_alert_fires_and_scales(client, auth_headers):
    # 2.5x the $1 ceiling -> warning.
    warn = _ingest_llm(client, auth_headers, "cost-warn", model="gpt-4o", cost_usd=2.5)
    rules = {a["rule"]: a for a in warn.json()["triggered_alerts"]}
    assert "cost_spike" in rules
    assert rules["cost_spike"]["severity"] == "warning"
    # >=3x the ceiling -> critical.
    crit = _ingest_llm(client, auth_headers, "cost-crit", cost_usd=5.0)
    crit_rules = {a["rule"]: a for a in crit.json()["triggered_alerts"]}
    assert crit_rules["cost_spike"]["severity"] == "critical"


def test_token_spike_alert(client, auth_headers):
    resp = _ingest_llm(
        client, auth_headers, "tok-wl", input_tokens=120_000, output_tokens=0
    )
    rules = {a["rule"] for a in resp.json()["triggered_alerts"]}
    assert "token_spike" in rules


def test_rate_limit_surge_alert(client, auth_headers):
    # Needs >= rate_limit_min_samples (5) and >= 20% rate-limited.
    last = None
    for _ in range(5):
        last = _ingest_llm(
            client, auth_headers, "rl-wl", status="error", error_type="rate_limit"
        )
    rules = {a["rule"] for a in last.json()["triggered_alerts"]}
    assert "rate_limit_surge" in rules


def test_llm_rules_dormant_for_http_workloads(client, auth_headers):
    """A plain HTTP-style sample (no LLM fields) trips no LLM-tuned rule."""
    resp = _ingest(client, auth_headers, "http-wl", latency=50)
    rules = {a["rule"] for a in resp.json()["triggered_alerts"]}
    assert rules.isdisjoint({"cost_spike", "token_spike", "rate_limit_surge"})
