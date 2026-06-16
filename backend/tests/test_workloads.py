def _ingest(client, headers, workload, latency=50, status="ok"):
    return client.post(
        "/metrics",
        json={"workload": workload, "latency_ms": latency, "status": status},
        headers=headers,
    )


def test_list_workloads_empty(client, auth_headers):
    resp = client.get("/workloads", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_workloads_after_ingest(client, auth_headers):
    _ingest(client, auth_headers, "wl-b")
    _ingest(client, auth_headers, "wl-a")
    resp = client.get("/workloads", headers=auth_headers)
    assert resp.status_code == 200
    names = [w["name"] for w in resp.json()]
    assert names == ["wl-a", "wl-b"]  # ordered by name


def test_list_workloads_requires_auth(client):
    assert client.get("/workloads").status_code == 401


# --- Seasonal baselines view ------------------------------------------------


def test_workload_baselines_requires_auth(client):
    assert client.get("/workloads/1/baselines").status_code == 401


def test_workload_baselines_missing_workload_404(client, auth_headers):
    resp = client.get("/workloads/999999/baselines", headers=auth_headers)
    assert resp.status_code == 404


def test_workload_baselines_empty_until_learned(client, auth_headers):
    wid = _ingest(client, auth_headers, "bl-wl").json()["sample"]["workload_id"]
    # No refresh has run, so nothing has been learned yet.
    resp = client.get(f"/workloads/{wid}/baselines", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_workload_baselines_populated_after_refresh(client, auth_headers):
    wid = None
    # Enough varied samples in the current hour to clear anomaly_bucket_min_samples
    # (20) with real spread, so the bucket is learned.
    for i in range(22):
        wid = _ingest(client, auth_headers, "bl-wl2", latency=50 + (i % 7)).json()[
            "sample"
        ]["workload_id"]
    assert (
        client.post("/admin/refresh-baselines", headers=auth_headers).status_code == 200
    )

    body = client.get(f"/workloads/{wid}/baselines", headers=auth_headers).json()
    latency = [b for b in body if b["metric"] == "latency"]
    assert len(latency) >= 1
    row = latency[0]
    assert set(row) == {"metric", "bucket", "center", "scale", "n"}
    assert row["n"] >= 20
    assert 0 <= row["bucket"] <= 23
