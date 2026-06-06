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
