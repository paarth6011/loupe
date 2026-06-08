import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool

from app.auth import decode_token
from app.database import get_session_factory
from app.models import Alert, MetricSample

router = APIRouter(tags=["events"])

# How often the server re-checks the DB for changes, and the maximum lifetime of
# a single SSE connection before the client transparently reconnects. EventSource
# reconnects on its own, so capping lifetime keeps a vanished client from holding
# resources indefinitely.
_POLL_SECONDS = 2.0
_MAX_CONNECTION_SECONDS = 300.0


def _read_fingerprint(session_factory: sessionmaker) -> tuple[int, int, int]:
    """A cheap snapshot of mutable state: the newest sample id, the newest alert
    id, and the count of currently-open alerts. Any change to this triple means
    the dashboard has something new to show and should refetch. Three small
    indexed aggregates — far cheaper than streaming the data itself."""
    with session_factory() as db:
        sample_max = db.scalar(select(func.max(MetricSample.id))) or 0
        alert_max = db.scalar(select(func.max(Alert.id))) or 0
        open_alerts = (
            db.scalar(
                select(func.count())
                .select_from(Alert)
                .where(Alert.resolved_at.is_(None))
            )
            or 0
        )
    return sample_max, alert_max, open_alerts


async def _event_stream(
    request: Request, session_factory: sessionmaker
) -> AsyncIterator[str]:
    """Server-Sent Events: emit a `changed` event whenever the data fingerprint
    moves, and a keepalive comment otherwise so the connection survives idle
    periods and proxies. The fingerprint read is the only blocking work, and it's
    pushed to a threadpool so the event loop stays free; the sleep is async."""
    last: tuple[int, int, int] | None = None
    started = time.monotonic()
    # Greet immediately so the client knows the stream is live.
    yield ": connected\n\n"
    while time.monotonic() - started < _MAX_CONNECTION_SECONDS:
        if await request.is_disconnected():
            break
        fingerprint = await run_in_threadpool(_read_fingerprint, session_factory)
        if fingerprint != last:
            last = fingerprint
            payload = json.dumps(
                {
                    "samples": fingerprint[0],
                    "alerts": fingerprint[1],
                    "open_alerts": fingerprint[2],
                }
            )
            yield f"event: changed\ndata: {payload}\n\n"
        else:
            yield ": keepalive\n\n"
        await asyncio.sleep(_POLL_SECONDS)


@router.get("/events")
def events(
    request: Request,
    token: str | None = Query(default=None),
    session_factory: sessionmaker = Depends(get_session_factory),
) -> StreamingResponse:
    """Live update stream. The dashboard opens this once and refetches whenever a
    `changed` event arrives, replacing fixed-interval polling.

    EventSource can't set an Authorization header, so the JWT is passed as the
    `token` query param and validated the same way as the bearer path. A 401 here
    is terminal (bad/expired token); the client stops reconnecting and logs out.
    """
    if token is None or decode_token(token) is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return StreamingResponse(
        _event_stream(request, session_factory),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Tell nginx (the frontend proxy) not to buffer the stream.
            "X-Accel-Buffering": "no",
        },
    )
