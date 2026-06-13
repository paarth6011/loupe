"""Pool-cycle regression, against real Postgres.

Reproduces the production incident where authenticated requests 500'd on every
call after the first: the RLS tenant-reset on the engine's ``checkin`` event ran
``SELECT set_config(...)`` and left the connection mid-transaction (INTRANS), so
the *next* checkout's ``pool_pre_ping`` blew up with "can't change 'autocommit'
now: connection in transaction status INTRANS".

SQLite can't exercise this — it has no connection pool checkin/pre_ping, no
INTRANS state, and the reset event is Postgres-only — so this runs only when
``TEST_DATABASE_URL`` points at Postgres (CI provides one). With ``pool_size=1``
and ``max_overflow=0`` the SAME connection is reused every iteration, so the
checkin reset and the following checkout's pre_ping run on it: the exact path
that broke. Before the fix this failed on iteration 2; it must now pass.
"""

import os

import pytest
from sqlalchemy import create_engine, event, text

from app.database import _reset_tenant_on_checkin

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL.startswith("postgresql"),
    reason="pool/pre_ping/INTRANS behaviour is Postgres-only; set TEST_DATABASE_URL",
)


def test_authed_request_cycles_through_the_pool_without_intrans():
    # One connection, reused: forces the checkin-reset -> next-checkout-pre_ping
    # path that the bug lived in. pool_pre_ping=True is what raised on INTRANS.
    engine = create_engine(
        TEST_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
    )
    event.listens_for(engine, "checkin")(_reset_tenant_on_checkin)
    try:
        # Several "requests" back to back. Each pins a tenant in a transaction
        # and commits, like a real request; closing the connection fires the
        # checkin reset. If that reset leaves the connection INTRANS, the next
        # iteration's pre_ping raises before we get here again.
        for _ in range(3):
            with engine.connect() as conn:
                conn.execute(
                    text("SELECT set_config('app.current_account', '1', false)")
                )
                conn.execute(text("SELECT 1"))
                conn.commit()
    finally:
        engine.dispose()
