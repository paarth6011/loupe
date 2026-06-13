from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


engine = create_engine(
    get_settings().runtime_database_url(),
    # Detect and replace connections the DB has dropped, on checkout.
    pool_pre_ping=True,
    # Proactively retire connections older than 30 min so stale/half-dead ones
    # don't pile up (the small prod VM drops idle connections under memory
    # pressure). Belt-and-braces with pool_pre_ping.
    pool_recycle=1800,
    # A little more headroom than the 5+10 default so a burst of concurrent
    # viewers (each SSE stream polls the DB) can't starve the request path.
    pool_size=10,
    max_overflow=20,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Postgres GUC that row-level security reads (see migration 0010). It names the
# tenant whose rows the current connection may see.
_IS_POSTGRES = engine.dialect.name == "postgresql"


def _reset_tenant_guc(dbapi_connection) -> None:
    """Clear the tenant pin on a raw DBAPI connection (raises if it's dead).

    Commit afterward so the connection re-enters the pool IDLE, not INTRANS. The
    reset SQL opens a transaction on the (non-autocommit) connection; a connection
    left mid-transaction makes the *next* checkout's pool_pre_ping blow up with
    "can't change 'autocommit' now: connection in transaction status INTRANS",
    500ing the request. The reset uses set_config(..., is_local=false) — session
    scope — so the cleared value persists across this commit and onto the next
    request, which is exactly what we want.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SELECT set_config('app.current_account', '', false)")
    finally:
        cursor.close()
    dbapi_connection.commit()


def _reset_tenant_on_checkin(dbapi_connection, connection_record) -> None:
    """Clear the tenant pin before a connection re-enters the pool.

    Without this, a pooled connection could carry one request's account_id into
    the next request. Combined with the fail-closed RLS policy (an empty setting
    becomes NULL and matches no rows), a missing pin therefore *denies* rather
    than leaks — the unset state is safe, a stale state would not be.

    Must NEVER raise. If the connection has already died (the small prod VM drops
    connections under memory pressure), running SQL here throws; letting that
    propagate out of the checkin event corrupts the pool's accounting and leaks
    the slot, until every slot is gone and the pool is permanently exhausted (the
    bug this guards against). On failure we skip the reset — pool_pre_ping
    discards the dead connection on its next checkout, and the fail-closed RLS
    policy keeps an unreset connection safe (it denies rows).
    """
    try:
        _reset_tenant_guc(dbapi_connection)
    except Exception:
        pass


if _IS_POSTGRES:
    # Only Postgres has the RLS GUC; SQLite (tests) has no per-connection state.
    event.listens_for(engine, "checkin")(_reset_tenant_on_checkin)


def set_current_account(db: Session, account_id: int) -> None:
    """Pin this session's connection to one tenant so row-level security scopes
    every subsequent query to it.

    Session-scoped (not ``SET LOCAL``) on purpose: the ingest path commits
    mid-request and keeps querying, and a transaction-local setting would be
    cleared by that commit, leaving the follow-up queries unpinned. The value is
    reset on connection checkin (above). No-op off Postgres — the SQLite test DB
    has no RLS and relies on the explicit ``account_id`` filters in app code.

    Keyed off the *session's* bind, not the app engine: the test suite runs a
    SQLite session even though the app's default engine is Postgres.
    """
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT set_config('app.current_account', :account_id, false)"),
        {"account_id": str(account_id)},
    )


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory() -> sessionmaker:
    """Dependency returning the session factory itself, for use in background
    tasks that run after the request's session is gone."""
    return SessionLocal
