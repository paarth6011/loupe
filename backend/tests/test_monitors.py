def _new_workload(client, headers, name):
    resp = client.post(
        "/metrics",
        json={"workload": name, "latency_ms": 50, "status": "ok"},
        headers=headers,
    )
    return resp.json()["sample"]["workload_id"]


def test_list_monitors_returns_all_rules_with_defaults(client, auth_headers):
    wid = _new_workload(client, auth_headers, "mon-wl")
    out = client.get(f"/workloads/{wid}/monitors", headers=auth_headers)
    assert out.status_code == 200
    by_rule = {m["rule"]: m for m in out.json()}
    assert len(by_rule) == 7  # full rule catalogue
    hl = by_rule["high_latency"]
    assert hl["enabled"] is True
    assert hl["threshold"] is None  # no override yet
    assert hl["default_threshold"] == 1000
    assert hl["effective_threshold"] == 1000
    assert hl["unit"] == "ms"
    assert by_rule["latency_anomaly"]["detector"] == "zscore"


def test_threshold_override_changes_firing(client, auth_headers):
    wid = _new_workload(client, auth_headers, "mon-thr")
    put = client.put(
        f"/workloads/{wid}/monitors/high_latency",
        json={"threshold": 200},
        headers=auth_headers,
    )
    assert put.status_code == 200
    assert put.json()["threshold"] == 200
    assert put.json()["effective_threshold"] == 200
    # 300ms is under the 1000ms default but over the 200ms override -> fires.
    resp = client.post(
        "/metrics",
        json={"workload": "mon-thr", "latency_ms": 300, "status": "ok"},
        headers=auth_headers,
    )
    rules = {a["rule"] for a in resp.json()["triggered_alerts"]}
    assert "high_latency" in rules


def test_disabling_rule_mutes_and_resolves_open_alert(client, auth_headers):
    wl = "mon-mute"
    first = client.post(
        "/metrics",
        json={"workload": wl, "latency_ms": 5000, "status": "ok"},
        headers=auth_headers,
    )
    wid = first.json()["sample"]["workload_id"]
    assert any(a["rule"] == "high_latency" for a in first.json()["triggered_alerts"])

    client.put(
        f"/workloads/{wid}/monitors/high_latency",
        json={"enabled": False},
        headers=auth_headers,
    )
    # Another breach, but the rule is muted: no new alert, and the open one clears.
    again = client.post(
        "/metrics",
        json={"workload": wl, "latency_ms": 5000, "status": "ok"},
        headers=auth_headers,
    )
    assert all(a["rule"] != "high_latency" for a in again.json()["triggered_alerts"])
    alerts = client.get(f"/alerts?workload_id={wid}", headers=auth_headers).json()
    hl = [a for a in alerts if a["rule"] == "high_latency"]
    assert hl and all(a["resolved_at"] is not None for a in hl)


def test_clearing_threshold_falls_back_to_default(client, auth_headers):
    wid = _new_workload(client, auth_headers, "mon-clr")
    client.put(
        f"/workloads/{wid}/monitors/high_latency",
        json={"threshold": 200},
        headers=auth_headers,
    )
    cleared = client.put(
        f"/workloads/{wid}/monitors/high_latency",
        json={"threshold": None},
        headers=auth_headers,
    )
    assert cleared.json()["threshold"] is None
    assert cleared.json()["effective_threshold"] == 1000


def test_update_unknown_rule_is_404(client, auth_headers):
    wid = _new_workload(client, auth_headers, "mon-unk")
    out = client.put(
        f"/workloads/{wid}/monitors/not_a_rule",
        json={"enabled": False},
        headers=auth_headers,
    )
    assert out.status_code == 404


def test_monitors_require_auth(client):
    assert client.get("/workloads/1/monitors").status_code == 401
