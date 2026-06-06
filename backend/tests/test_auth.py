from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_success_and_me():
    """Happy path: valid creds yield a token that authenticates /auth/me."""
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
