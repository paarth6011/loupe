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
