from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Postgres GUC that row-level security reads (see migration 0010). It names the
# tenant whose rows the current connection may see.
_IS_POSTGRES = engine.dialect.name == "postgresql"


if _IS_POSTGRES:

    @event.listens_for(engine, "checkin")
    def _reset_tenant_on_checkin(dbapi_connection, connection_record) -> None:
        """Clear the tenant pin before a connection re-enters the pool.

        Without this, a pooled connection could carry one request's account_id
        into the next request. Combined with the fail-closed RLS policy (an empty
        setting becomes NULL and matches no rows), a missing pin therefore *denies*
        rather than leaks — the unset state is safe, a stale state would not be.
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SELECT set_config('app.current_account', '', false)")
        finally:
            cursor.close()


def set_current_account(db: Session, account_id: int) -> None:
    """Pin this session's connection to one tenant so row-level security scopes
    every subsequent query to it.

    Session-scoped (not ``SET LOCAL``) on purpose: the ingest path commits
    mid-request and keeps querying, and a transaction-local setting would be
    cleared by that commit, leaving the follow-up queries unpinned. The value is
    reset on connection checkin (above). No-op off Postgres — the SQLite test DB
    has no RLS and relies on the explicit ``account_id`` filters in app code.
    """
    if not _IS_POSTGRES:
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
