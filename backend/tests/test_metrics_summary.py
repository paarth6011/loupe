from datetime import timedelta

import pytest

from app.aggregation import parse_window, percentile


def test_parse_window_units():
    assert parse_window("30s") == timedelta(seconds=30)
    assert parse_window("15m") == timedelta(minutes=15)
    assert parse_window("2h") == timedelta(hours=2)
    assert parse_window("1d") == timedelta(days=1)


def test_parse_window_invalid():
    with pytest.raises(ValueError):
        parse_window("nonsense")


def test_percentile_basic():
    vals = [100, 200, 300, 400, 500]
    assert percentile(vals, 50) == 300
    assert percentile(vals, 95) == 480
    assert percentile([], 50) is None


def _ingest(client, headers, workload, latency, status="ok"):
    return client.post(
        "/metrics",
        json={"workload": workload, "latency_ms": latency, "status": status},
        headers=headers,
    )


def test_summary_counts_and_percentiles(client, auth_headers):
    resp = None
    for lat in [100, 200, 300, 400, 500]:
        resp = _ingest(client, auth_headers, "sum-wl", lat)
    workload_id = resp.json()["sample"]["workload_id"]

    out = client.get(
        f"/metrics/summary?workload_id={workload_id}&window=1h", headers=auth_headers
    )
    assert out.status_code == 200
    body = out.json()
    assert body["request_count"] == 5
    assert body["error_count"] == 0
    assert body["error_rate"] == 0.0
    assert body["latency_p50_ms"] == 300
    assert body["latency_p95_ms"] == 480


def test_summary_error_rate(client, auth_headers):
    resp = None
    for st in ["ok", "error", "ok", "error", "ok"]:
        resp = _ingest(client, auth_headers, "err-wl", 50, st)
    workload_id = resp.json()["sample"]["workload_id"]

    body = client.get(
        f"/metrics/summary?workload_id={workload_id}&window=1h", headers=auth_headers
    ).json()
    assert body["request_count"] == 5
    assert body["error_count"] == 2
    assert body["error_rate"] == 0.4


def test_summary_invalid_window(client, auth_headers):
    resp = _ingest(client, auth_headers, "win-wl", 50)
    workload_id = resp.json()["sample"]["workload_id"]
    out = client.get(
        f"/metrics/summary?workload_id={workload_id}&window=abc", headers=auth_headers
    )
    assert out.status_code == 422


def test_summary_unknown_workload(client, auth_headers):
    out = client.get(
        "/metrics/summary?workload_id=99999&window=1h", headers=auth_headers
    )
    assert out.status_code == 404


def test_summary_requires_auth(client):
    out = client.get("/metrics/summary?workload_id=1&window=1h")
    assert out.status_code == 401


def test_summary_is_cached_within_ttl(client, auth_headers):
    """A second identical request is served from cache, so new samples between
    the two calls don't change the result; a different window bypasses it."""
    resp = None
    for lat in [100, 200]:
        resp = _ingest(client, auth_headers, "cache-wl", lat)
    workload_id = resp.json()["sample"]["workload_id"]

    first = client.get(
        f"/metrics/summary?workload_id={workload_id}&window=1h", headers=auth_headers
    ).json()
    assert first["request_count"] == 2

    _ingest(client, auth_headers, "cache-wl", 300)  # new sample, not yet visible
    cached = client.get(
        f"/metrics/summary?workload_id={workload_id}&window=1h", headers=auth_headers
    ).json()
    assert cached["request_count"] == 2  # served from cache

    # A different window is a different cache key -> freshly computed.
    fresh = client.get(
        f"/metrics/summary?workload_id={workload_id}&window=15m", headers=auth_headers
    ).json()
    assert fresh["request_count"] == 3
