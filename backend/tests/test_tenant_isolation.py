"""The Phase-1 guarantee, proven against real Postgres: one account cannot read
another account's rows — *even with a query that forgets to filter by account*.

This is the test the whole tenancy phase exists for. It cannot run on SQLite
(no row-level security), so it is skipped unless ``TEST_DATABASE_URL`` points at
a Postgres instance. CI provides one (see .github/workflows/ci.yml).

Why a restricted role: superusers (and table owners, absent FORCE) bypass RLS.
The migration uses FORCE ROW LEVEL SECURITY and the app connects as a
non-superuser role; this test reproduces that by ``SET ROLE`` to a non-superuser
before the bare SELECT, so the policy actually binds.
"""

import os

import pytest
from sqlalchemy import create_engine, text

from app.database import Base

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL.startswith("postgresql"),
    reason="RLS isolation is Postgres-only; set TEST_DATABASE_URL to a Postgres DSN",
)

# A non-superuser, non-owner role so RLS is enforced (not bypassed) on reads.
RLS_ROLE = "loupe_rls_test"

# The same policy the 0010 migration installs: an unset/empty GUC becomes NULL
# and matches no rows (fail closed). Kept as a flat string so the formatter never
# rewraps the SQL.
_POLICY_SQL = "CREATE POLICY tenant_isolation ON workloads USING (account_id = NULLIF(current_setting('app.current_account', true), '')::int) WITH CHECK (account_id = NULLIF(current_setting('app.current_account', true), '')::int)"  # noqa: E501

_ENABLE_RLS = [
    "ALTER TABLE workloads ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE workloads FORCE ROW LEVEL SECURITY",
    _POLICY_SQL,
]

_INSERT_ACCOUNT = "INSERT INTO accounts (name) VALUES (:name) RETURNING id"
_INSERT_WORKLOAD = "INSERT INTO workloads (account_id, name) VALUES (:acct, :name)"
_SELECT_ALL = "SELECT account_id FROM workloads ORDER BY account_id"
_SET_ACCOUNT = "SELECT set_config('app.current_account', :account, false)"

_CREATE_ROLE = f"""
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{RLS_ROLE}') THEN
    CREATE ROLE {RLS_ROLE} NOSUPERUSER;
  END IF;
END $$;
"""

_DROP_ROLE = f"""
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{RLS_ROLE}') THEN
    EXECUTE 'DROP OWNED BY {RLS_ROLE}';
    DROP ROLE {RLS_ROLE};
  END IF;
END $$;
"""


@pytest.fixture
def pg_engine():
    """A fresh Postgres schema with RLS on `workloads`, two tenants each owning a
    workload, and a non-superuser role granted SELECT. Torn down after."""
    engine = create_engine(TEST_DATABASE_URL)

    # Start from a clean slate (a previous failed run may have left tables/role).
    with engine.begin() as conn:
        conn.execute(text(_DROP_ROLE))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        for stmt in _ENABLE_RLS:
            conn.execute(text(stmt))
        conn.execute(text(_CREATE_ROLE))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {RLS_ROLE}"))
        conn.execute(text(f"GRANT SELECT ON workloads TO {RLS_ROLE}"))

        # Two tenants, one workload each. Inserted as the superuser, which
        # bypasses RLS — so the setup itself isn't constrained by the policy.
        a_id = conn.execute(text(_INSERT_ACCOUNT), {"name": "tenant-a"}).scalar_one()
        b_id = conn.execute(text(_INSERT_ACCOUNT), {"name": "tenant-b"}).scalar_one()
        conn.execute(text(_INSERT_WORKLOAD), {"acct": a_id, "name": "wl-a"})
        conn.execute(text(_INSERT_WORKLOAD), {"acct": b_id, "name": "wl-b"})

    try:
        yield engine, a_id, b_id
    finally:
        Base.metadata.drop_all(engine)
        with engine.begin() as conn:
            conn.execute(text(_DROP_ROLE))
        engine.dispose()


def _visible_account_ids(conn) -> list[int]:
    """account_ids returned by a *bare* SELECT — no WHERE account_id filter. What
    comes back is purely whatever RLS lets this connection see."""
    rows = conn.execute(text(_SELECT_ALL))
    return [r[0] for r in rows]


def test_account_sees_only_its_own_rows(pg_engine):
    engine, a_id, b_id = pg_engine
    with engine.connect() as conn:
        # Become the restricted role so RLS is enforced, not bypassed.
        conn.execute(text(f"SET ROLE {RLS_ROLE}"))

        # Pinned to A: a query that forgets to filter still returns only A's row.
        conn.execute(text(_SET_ACCOUNT), {"account": str(a_id)})
        assert _visible_account_ids(conn) == [a_id]

        # Pinned to B: now only B's row — A's is invisible.
        conn.execute(text(_SET_ACCOUNT), {"account": str(b_id)})
        assert _visible_account_ids(conn) == [b_id]

        conn.execute(text("RESET ROLE"))


def test_unset_account_is_fail_closed(pg_engine):
    """No pin at all must reveal *nothing* (deny), never everything. This is the
    property that makes a connection returned to the pool with a cleared GUC safe
    rather than a leak."""
    engine, _a_id, _b_id = pg_engine
    with engine.connect() as conn:
        conn.execute(text(f"SET ROLE {RLS_ROLE}"))
        conn.execute(text(_SET_ACCOUNT), {"account": ""})
        assert _visible_account_ids(conn) == []
        conn.execute(text("RESET ROLE"))
