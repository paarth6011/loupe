def _ingest(client, headers, workload, latency=50, status="ok"):
    return client.post(
        "/metrics",
        json={"workload": workload, "latency_ms": latency, "status": status},
        headers=headers,
    )


def test_timeseries_buckets_and_counts(client, auth_headers):
    resp = None
    for lat in [100, 200, 300, 400]:
        resp = _ingest(client, auth_headers, "ts-wl", lat)
    workload_id = resp.json()["sample"]["workload_id"]

    out = client.get(
        f"/metrics/timeseries?workload_id={workload_id}&window=1h&bucket=5m",
        headers=auth_headers,
    )
    assert out.status_code == 200
    body = out.json()
    assert body["bucket"] == "5m"
    points = body["points"]
    assert len(points) == 12  # 1h / 5m

    # All just-ingested samples land in the final bucket; counts sum to total.
    assert sum(p["request_count"] for p in points) == 4
    last = points[-1]
    assert last["request_count"] == 4
    assert last["latency_p50_ms"] is not None

    # Empty buckets are present with zeroed stats.
    assert points[0]["request_count"] == 0
    assert points[0]["latency_p50_ms"] is None


def test_timeseries_bucket_larger_than_window(client, auth_headers):
    resp = _ingest(client, auth_headers, "ts-wl2", 50)
    workload_id = resp.json()["sample"]["workload_id"]
    out = client.get(
        f"/metrics/timeseries?workload_id={workload_id}&window=5m&bucket=1h",
        headers=auth_headers,
    )
    assert out.status_code == 422


def test_timeseries_too_many_buckets(client, auth_headers):
    resp = _ingest(client, auth_headers, "ts-wl3", 50)
    workload_id = resp.json()["sample"]["workload_id"]
    out = client.get(
        f"/metrics/timeseries?workload_id={workload_id}&window=24h&bucket=1s",
        headers=auth_headers,
    )
    assert out.status_code == 422


def test_timeseries_unknown_workload(client, auth_headers):
    out = client.get(
        "/metrics/timeseries?workload_id=99999&window=1h&bucket=5m",
        headers=auth_headers,
    )
    assert out.status_code == 404


def test_timeseries_requires_auth(client):
    out = client.get("/metrics/timeseries?workload_id=1&window=1h&bucket=5m")
    assert out.status_code == 401
