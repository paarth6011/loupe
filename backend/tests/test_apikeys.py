def _create_key(client, headers, name="sdk-prod"):
    return client.post("/apikeys", json={"name": name}, headers=headers)


def test_create_key_returns_plaintext_once(client, auth_headers):
    resp = _create_key(client, auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["key"].startswith("loupe_sk_")
    assert body["name"] == "sdk-prod"
    assert body["prefix"].startswith("loupe_sk_")
    # The prefix is a short, non-secret slice of the full key.
    assert body["key"].startswith(body["prefix"])


def test_list_keys_never_exposes_secret(client, auth_headers):
    _create_key(client, auth_headers, "k1")
    resp = client.get("/apikeys", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert "key" not in rows[0]  # only prefix is returned
    assert rows[0]["prefix"].startswith("loupe_sk_")


def test_ingest_with_api_key(client, auth_headers):
    key = _create_key(client, auth_headers).json()["key"]
    resp = client.post(
        "/metrics",
        json={"workload": "via-key", "latency_ms": 100, "status": "ok"},
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 201


def test_ingest_with_bad_key_is_401(client):
    resp = client.post(
        "/metrics",
        json={"workload": "nope", "latency_ms": 100, "status": "ok"},
        headers={"X-API-Key": "loupe_sk_not_a_real_key"},
    )
    assert resp.status_code == 401


def test_revoked_key_stops_working(client, auth_headers):
    created = _create_key(client, auth_headers).json()
    key = created["key"]
    # Works before revocation.
    ok = client.post(
        "/metrics",
        json={"workload": "rev-wl", "latency_ms": 100, "status": "ok"},
        headers={"X-API-Key": key},
    )
    assert ok.status_code == 201
    # Revoke, then it is rejected.
    assert (
        client.delete(f"/apikeys/{created['id']}", headers=auth_headers).status_code
        == 204
    )
    after = client.post(
        "/metrics",
        json={"workload": "rev-wl", "latency_ms": 100, "status": "ok"},
        headers={"X-API-Key": key},
    )
    assert after.status_code == 401


def test_ingest_still_works_with_admin_jwt(client, auth_headers):
    # Back-compat: the dashboard/manual posting path keeps working.
    resp = client.post(
        "/metrics",
        json={"workload": "via-jwt", "latency_ms": 100, "status": "ok"},
        headers=auth_headers,
    )
    assert resp.status_code == 201


def test_ingest_without_any_auth_is_401(client):
    resp = client.post(
        "/metrics",
        json={"workload": "no-auth", "latency_ms": 100, "status": "ok"},
    )
    assert resp.status_code == 401


def test_apikey_management_requires_admin(client):
    assert client.get("/apikeys").status_code == 401
    assert client.post("/apikeys", json={"name": "x"}).status_code == 401
