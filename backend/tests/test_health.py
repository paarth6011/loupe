from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_ok(client):
    """Readiness passes when DB and cache are reachable (in-memory in tests)."""
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"db": True, "redis": True}


def test_ready_503_when_redis_down(client):
    """Readiness returns 503 if a dependency check fails."""
    from app.cache import get_cache
    from app.main import app as fastapi_app

    class BrokenCache:
        def get(self, key):
            return None  # never reflects the written value

        def set(self, key, value, ttl_seconds):
            pass

    fastapi_app.dependency_overrides[get_cache] = lambda: BrokenCache()
    try:
        resp = client.get("/ready")
        assert resp.status_code == 503
        assert resp.json()["detail"]["checks"]["redis"] is False
    finally:
        # Restore the fixture's cache override by removing ours; fixture teardown
        # clears all overrides anyway.
        del fastapi_app.dependency_overrides[get_cache]
