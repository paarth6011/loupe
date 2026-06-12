"""Provision the restricted runtime role so row-level security actually binds.

The app serves requests as a NON-superuser role (``app_db_user``); superusers
and BYPASSRLS roles skip RLS, so without this the tenant policies installed by
migration 0010 would be dormant. Migrations still run as the privileged owner
(``database_url``); this only creates the restricted role and grants it DML on
the app schema. Idempotent — meant to run on every boot, after migrations.

No-op unless ``app_db_password`` is set (dev, tests, and single-tenant self-host
serve directly as the owner, where RLS bypass is harmless: there is one tenant).
"""

import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.config import get_settings

# Run once the tables exist (after migrations). Default privileges also cover
# tables future migrations create, since those run as this same owner role.
_GRANTS = [
    "GRANT CONNECT ON DATABASE {d} TO {r}",
    "GRANT USAGE ON SCHEMA public TO {r}",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {r}",
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {r}",
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {r}",
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {r}",
]


def _admin_dsn(database_url: str) -> str:
    # psycopg wants a plain libpq URL, not SQLAlchemy's "+psycopg" dialect URL.
    url = make_url(database_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


def ensure_app_role() -> None:
    settings = get_settings()
    user = settings.app_db_user
    password = settings.app_db_password
    if not password:
        print(
            "app_db_password unset; serving as owner role (RLS not enforced)",
            file=sys.stderr,
        )
        return

    role = sql.Identifier(user)
    with psycopg.connect(_admin_dsn(settings.database_url), autocommit=True) as conn:
        database = sql.Identifier(conn.info.dbname)
        # Create the role if missing, then (re)assert its attributes + password
        # every boot so a rotated password takes effect and the role can never
        # drift into superuser/BYPASSRLS.
        conn.execute(
            sql.SQL(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = {u}) THEN "
                "CREATE ROLE {r} LOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$;"
            ).format(u=sql.Literal(user), r=role)
        )
        conn.execute(
            sql.SQL(
                "ALTER ROLE {r} WITH LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {p}"
            ).format(r=role, p=sql.Literal(password))
        )
        for stmt in _GRANTS:
            conn.execute(sql.SQL(stmt).format(d=database, r=role))
    print(f"ensured restricted runtime role: {user}", file=sys.stderr)


if __name__ == "__main__":
    ensure_app_role()
