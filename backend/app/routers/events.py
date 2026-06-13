import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool

from app.auth import decode_stream_ticket_account
from app.database import get_session_factory, set_current_account
from app.models import Alert, MetricSample

router = APIRouter(tags=["events"])

# How often the server re-checks the DB for changes, and the maximum lifetime of
# a single SSE connection before the client transparently reconnects. EventSource
# reconnects on its own, so capping lifetime keeps a vanished client from holding
# resources indefinitely. The poll interval is a per-viewer DB hit, so it's kept
# coarse; many concurrent viewers would still warrant a shared poller.
_POLL_SECONDS = 3.0
_MAX_CONNECTION_SECONDS = 300.0


def _read_fingerprint(
    session_factory: sessionmaker, account_id: int
) -> tuple[int, int, int]:
    """A cheap snapshot of one tenant's mutable state: the newest sample id, the
    newest alert id, and the count of currently-open alerts. Any change to this
    triple means the dashboard has something new to show and should refetch.
    Three small indexed aggregates — far cheaper than streaming the data itself.

    Scoped to the viewer's account both ways: the session is pinned for
    row-level security (Postgres), and the queries filter by account_id
    explicitly (so the SQLite path is scoped too, and intent is obvious)."""
    with session_factory() as db:
        set_current_account(db, account_id)
        sample_max = (
            db.scalar(
                select(func.max(MetricSample.id)).where(
                    MetricSample.account_id == account_id
                )
            )
            or 0
        )
        alert_max = (
            db.scalar(select(func.max(Alert.id)).where(Alert.account_id == account_id))
            or 0
        )
        open_alerts = (
            db.scalar(
                select(func.count())
                .select_from(Alert)
                .where(Alert.account_id == account_id, Alert.resolved_at.is_(None))
            )
            or 0
        )
    return sample_max, alert_max, open_alerts


async def _event_stream(
    request: Request, session_factory: sessionmaker, account_id: int
) -> AsyncIterator[str]:
    """Server-Sent Events: emit a `changed` event whenever the data fingerprint
    moves, and a keepalive comment otherwise so the connection survives idle
    periods and proxies. The fingerprint read is the only blocking work, and it's
    pushed to a threadpool so the event loop stays free; the sleep is async.

    The fingerprint is scoped to ``account_id`` so a viewer is only woken by
    changes within their own tenant."""
    last: tuple[int, int, int] | None = None
    started = time.monotonic()
    # Greet immediately so the client knows the stream is live.
    yield ": connected\n\n"
    while time.monotonic() - started < _MAX_CONNECTION_SECONDS:
        if await request.is_disconnected():
            break
        fingerprint = await run_in_threadpool(
            _read_fingerprint, session_factory, account_id
        )
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
    ticket: str | None = Query(default=None),
    session_factory: sessionmaker = Depends(get_session_factory),
) -> StreamingResponse:
    """Live update stream. The dashboard opens this once and refetches whenever a
    `changed` event arrives, replacing fixed-interval polling.

    EventSource can't set an Authorization header, so authentication uses a
    short-lived, read-only *stream ticket* (minted via POST /auth/stream-ticket)
    passed as the `ticket` query param — never the full admin JWT, which would
    otherwise leak into proxy logs and browser history. The ticket carries the
    viewer's account, which scopes the stream to their tenant. A 401 here is
    terminal for this connection; the client mints a fresh ticket and reconnects.
    """
    account_id = decode_stream_ticket_account(ticket) if ticket else None
    if account_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return StreamingResponse(
        _event_stream(request, session_factory, account_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Tell nginx (the frontend proxy) not to buffer the stream.
            "X-Accel-Buffering": "no",
        },
    )
