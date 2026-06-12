from fastapi.testclient import TestClient

from app.auth import (
    create_access_token,
    create_stream_ticket,
    decode_stream_ticket,
    decode_token,
)
from app.main import app

client = TestClient(app)


def test_login_success_and_me(client):
    """Happy path: valid creds yield a token that authenticates /auth/me.

    Uses the fixture client (in-memory DB with the default account seeded), since
    /auth/me now resolves the caller's account via a DB lookup.
    """
    resp = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    token = body["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


def test_login_wrong_password():
    """Failure path: bad credentials are rejected with 401."""
    resp = client.post("/auth/login", json={"username": "admin", "password": "nope"})
    assert resp.status_code == 401


def test_me_requires_token():
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_invalid_token():
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401


# --- Stream tickets (C1): a narrow, scope-separated credential -----------------


def test_stream_ticket_and_access_token_are_scope_separated():
    """An admin access token must not pass as a stream ticket, and vice versa —
    so a URL-borne ticket can never be replayed against admin/ingest endpoints."""
    access = create_access_token("admin")
    ticket = create_stream_ticket("admin", account_id=1)

    assert decode_token(access) == "admin"
    assert decode_stream_ticket(ticket) == "admin"
    # Cross-use is rejected both directions.
    assert decode_stream_ticket(access) is None
    assert decode_token(ticket) is None


def test_stream_ticket_endpoint_requires_auth_and_returns_usable_ticket(
    client, auth_headers
):
    assert client.post("/auth/stream-ticket").status_code == 401
    resp = client.post("/auth/stream-ticket", headers=auth_headers)
    assert resp.status_code == 200
    assert decode_stream_ticket(resp.json()["ticket"]) == "admin"


# --- Frictionless dev login ---------------------------------------------------


def test_dev_login_issues_admin_token_in_dev(client):
    resp = client.post("/auth/dev-login")
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    assert decode_token(token) == "admin"
    # The token is a real, general-purpose admin token: it authenticates /me.
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


def test_dev_login_disabled_in_production(client):
    from app.config import Settings, get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(environment="production")
    try:
        assert client.post("/auth/dev-login").status_code == 404
    finally:
        app.dependency_overrides.pop(get_settings, None)


# --- Brute-force protection (M1) ----------------------------------------------


def test_login_throttles_after_repeated_failures(client):
    # Uses the fixture client (deterministic in-memory cache). Ten bad attempts
    # are 401; the next is refused with 429 regardless of the password.
    for _ in range(10):
        bad = client.post("/auth/login", json={"username": "admin", "password": "nope"})
        assert bad.status_code == 401
    locked = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert locked.status_code == 429


def test_login_success_resets_failure_counter(client):
    for _ in range(3):
        client.post("/auth/login", json={"username": "admin", "password": "nope"})
    ok = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert ok.status_code == 200
    # Counter cleared, so a fresh run of failures starts from zero (still 401).
    again = client.post("/auth/login", json={"username": "admin", "password": "nope"})
    assert again.status_code == 401
