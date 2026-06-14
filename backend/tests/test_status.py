from datetime import datetime, timezone

from app.models import Alert, MetricSample, Workload


def _ingest(client, auth_headers, workload, **fields):
    payload = {"workload": workload, "latency_ms": 50, "status": "ok", **fields}
    return client.post("/metrics", json=payload, headers=auth_headers)


def _make_public(client, auth_headers, name):
    """Find a workload by name and publish it on the status page."""
    wls = client.get("/workloads", headers=auth_headers).json()
    wid = next(w["id"] for w in wls if w["name"] == name)
    resp = client.patch(
        f"/workloads/{wid}", json={"public": True}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["public"] is True
    return wid


def test_status_is_public_no_auth(client):
    # No token required, and with nothing published the page is operational/empty.
    resp = client.get("/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall"] == "operational"
    assert body["components"] == []


def test_status_only_shows_published_workloads(client, auth_headers):
    _ingest(client, auth_headers, "public-svc")
    _ingest(client, auth_headers, "private-svc")
    _make_public(client, auth_headers, "public-svc")

    body = client.get("/status").json()
    names = [c["name"] for c in body["components"]]
    assert names == ["public-svc"]  # private-svc stays hidden
    comp = body["components"][0]
    assert comp["status"] == "operational"
    assert comp["uptime_24h"] == 100.0
    assert comp["latency_p50_ms"] == 50


def test_status_reflects_open_critical_alert(
    client, auth_headers, db_session, account_id
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    wl = Workload(account_id=account_id, name="down-svc", public=True)
    db_session.add(wl)
    db_session.flush()
    db_session.add(
        MetricSample(
            account_id=account_id,
            workload_id=wl.id,
            latency_ms=50,
            status="error",
            ts=now,
        )
    )
    db_session.add(
        Alert(
            account_id=account_id,
            workload_id=wl.id,
            rule="high_latency",
            message="m",
            severity="critical",
            triggered_at=now,
            resolved_at=None,
        )
    )
    db_session.commit()

    body = client.get("/status").json()
    comp = next(c for c in body["components"] if c["name"] == "down-svc")
    assert comp["status"] == "down"
    assert body["overall"] == "down"


def test_status_unknown_when_stale(client, auth_headers, db_session, account_id):
    # A published workload with no recent samples is "unknown", not operational.
    wl = Workload(account_id=account_id, name="stale-svc", public=True)
    db_session.add(wl)
    db_session.commit()

    body = client.get("/status").json()
    comp = next(c for c in body["components"] if c["name"] == "stale-svc")
    assert comp["status"] == "unknown"
    assert comp["uptime_24h"] is None
    assert body["overall"] == "degraded"  # unknown rolls up to partial degradation


def test_patch_workload_requires_auth(client, auth_headers):
    _ingest(client, auth_headers, "needs-auth-svc")
    wls = client.get("/workloads", headers=auth_headers).json()
    wid = next(w["id"] for w in wls if w["name"] == "needs-auth-svc")
    assert client.patch(f"/workloads/{wid}", json={"public": True}).status_code == 401


def test_status_excludes_other_tenants_public_workloads(
    client, auth_headers, db_session
):
    # The public status page is scoped to the default account. A *different*
    # tenant's public workload must never appear on it — even on a deploy where
    # RLS is bypassed, the explicit account_id filter keeps tenants from leaking
    # onto one shared page.
    from app.models import Account, Workload

    _ingest(client, auth_headers, "mine-svc")
    _make_public(client, auth_headers, "mine-svc")

    other = Account(name="other-tenant")
    db_session.add(other)
    db_session.flush()
    db_session.add(Workload(account_id=other.id, name="other-svc", public=True))
    db_session.commit()

    names = [c["name"] for c in client.get("/status").json()["components"]]
    assert names == ["mine-svc"]
    assert "other-svc" not in names
