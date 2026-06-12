"""multitenant: accounts, users, account_id + row-level security

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-12

Introduces tenancy (see docs/multi-tenancy.md):
  * new `accounts` and `users` tables,
  * `account_id` on every domain table, backfilled to a single "default" account
    so the existing single-tenant deploy's data is preserved,
  * workload names become unique *per account* (not globally),
  * Postgres row-level security on the four data tables so one account can never
    read another's rows — even via a query that forgets to filter by account.

RLS is enabled on workloads/metric_samples/alerts/monitors only. accounts,
users and api_keys are the identity/auth-bootstrap tables: the API-key hash
lookup and the login-by-email lookup both run *before* a tenant is established,
so they are scoped in application code (explicit account_id filters) rather than
by RLS, which would otherwise deny the very lookup that determines the tenant.

For RLS to actually bind, the application must connect as a NON-superuser role
(superusers carry BYPASSRLS). FORCE ROW LEVEL SECURITY below also subjects the
table owner to the policies. Provisioning that role / connection string is a
deploy step, documented in docs/multi-tenancy.md.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every domain table gains account_id and is backfilled to the default account.
TENANT_TABLES = ["workloads", "metric_samples", "alerts", "monitors", "api_keys"]
# Of those, these four enforce isolation in the database via RLS. (The rest are
# the auth-bootstrap tables — see the module docstring.)
RLS_TABLES = ["workloads", "metric_samples", "alerts", "monitors"]


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # --- new identity tables --------------------------------------------------
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "plan", sa.String(length=32), server_default="free", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "role", sa.String(length=16), server_default="owner", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_users_account_id"), "users", ["account_id"])
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # --- add account_id (nullable), then backfill, then enforce ---------------
    for table in TENANT_TABLES:
        op.add_column(table, sa.Column("account_id", sa.Integer(), nullable=True))

    # One default account inherits all pre-existing (single-tenant) rows.
    op.execute("INSERT INTO accounts (name, plan) VALUES ('default', 'free')")
    for table in TENANT_TABLES:
        op.execute(
            f"UPDATE {table} SET account_id = "
            "(SELECT id FROM accounts WHERE name = 'default' ORDER BY id LIMIT 1) "
            "WHERE account_id IS NULL"
        )

    for table in TENANT_TABLES:
        op.alter_column(table, "account_id", nullable=False)
        op.create_index(f"ix_{table}_account_id", table, ["account_id"])
        op.create_foreign_key(
            f"fk_{table}_account_id",
            table,
            "accounts",
            ["account_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # workload names: global-unique -> unique per account.
    op.drop_index("ix_workloads_name", table_name="workloads")
    op.create_index("ix_workloads_name", "workloads", ["name"])  # non-unique lookup
    op.create_unique_constraint(
        "uq_workload_account_name", "workloads", ["account_id", "name"]
    )

    # account-wide windows (e.g. /metrics/cost) span every workload in a tenant.
    op.create_index(
        "ix_samples_account_ts", "metric_samples", ["account_id", "ts"]
    )

    # --- row-level security (Postgres only) -----------------------------------
    if is_pg:
        for table in RLS_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            # NULLIF(...,'') so an unset/empty app.current_account yields NULL and
            # the comparison matches nothing (fail closed). missing_ok=true keeps
            # current_setting from erroring when the GUC was never set.
            op.execute(
                f"CREATE POLICY tenant_isolation ON {table} "
                "USING (account_id = "
                "NULLIF(current_setting('app.current_account', true), '')::int) "
                "WITH CHECK (account_id = "
                "NULLIF(current_setting('app.current_account', true), '')::int)"
            )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        for table in RLS_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_samples_account_ts", table_name="metric_samples")
    op.drop_constraint("uq_workload_account_name", "workloads", type_="unique")
    op.drop_index("ix_workloads_name", table_name="workloads")
    op.create_index("ix_workloads_name", "workloads", ["name"], unique=True)

    for table in TENANT_TABLES:
        op.drop_constraint(f"fk_{table}_account_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_account_id", table_name=table)
        op.drop_column(table, "account_id")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_account_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("accounts")
