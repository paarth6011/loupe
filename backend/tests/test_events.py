import asyncio
import json

from sqlalchemy.orm import sessionmaker

from app.models import MetricSample, Workload
from app.routers import events


def test_events_requires_ticket(client):
    # No ticket -> 401 before any streaming begins.
    assert client.get("/events").status_code == 401


def test_events_rejects_bad_ticket(client):
    assert client.get("/events?ticket=not-a-real-jwt").status_code == 401


def test_events_rejects_plain_admin_token(client, auth_headers):
    # A full admin JWT must NOT be usable as a stream ticket (scope separation):
    # the stream credential is deliberately narrow, so the broad token is refused.
    admin_jwt = auth_headers["Authorization"].split(" ", 1)[1]
    assert client.get(f"/events?ticket={admin_jwt}").status_code == 401


class _FakeRequest:
    """Stands in for a Starlette Request: reports connected for the first few
    polls, then disconnected so the stream loop exits promptly."""

    def __init__(self, connected_polls: int = 1) -> None:
        self._polls = 0
        self._connected_polls = connected_polls

    async def is_disconnected(self) -> bool:
        self._polls += 1
        return self._polls > self._connected_polls


def _seed_sample(db_engine) -> sessionmaker:
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    with factory() as db:
        wl = Workload(name="sse-wl")
        db.add(wl)
        db.flush()
        db.add(MetricSample(workload_id=wl.id, latency_ms=50, status="ok"))
        db.commit()
    return factory


def test_read_fingerprint_reflects_state(db_engine):
    factory = _seed_sample(db_engine)
    sample_max, alert_max, open_alerts = events._read_fingerprint(factory)
    assert sample_max >= 1
    assert alert_max == 0  # no alerts seeded
    assert open_alerts == 0


def test_event_stream_emits_changed(db_engine, monkeypatch):
    # Drive the async generator directly (the TestClient can't cleanly tear down
    # a long-lived SSE stream). No real sleeping between polls.
    monkeypatch.setattr(events, "_POLL_SECONDS", 0)
    factory = _seed_sample(db_engine)
    request = _FakeRequest(connected_polls=1)

    async def collect() -> list[str]:
        chunks: list[str] = []
        async for chunk in events._event_stream(request, factory):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(collect())

    # The greeting comes first, then a `changed` event carrying the fingerprint.
    assert chunks[0].startswith(": connected")
    changed = [c for c in chunks if c.startswith("event: changed")]
    assert changed, f"no changed event in {chunks}"
    payload = json.loads(changed[0].split("data:", 1)[1].strip())
    assert payload["samples"] >= 1
    assert "alerts" in payload and "open_alerts" in payload
