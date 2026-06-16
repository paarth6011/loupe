"""seasonal baseline profiles for anomaly detection

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-16

Adds `baseline_profiles`: a per-(workload, metric, hour-of-day) robust baseline
(median + MAD) that the anomaly detector compares recent calls against, so a
workload with a daily rhythm (e.g. always slow at 9am) is judged against its own
typical 9am rather than the quieter calls just before it. Rows are disposable
derived state, recomputed in full by a background job (see app/baselines.py).

The table is tenant-scoped, so it gets the same row-level security treatment as
the other domain tables (migration 0010): RLS enabled + FORCE, with the
`tenant_isolation` policy keyed on the `app.current_account` GUC. The background
refresh pins each account in turn, so it reads/writes under the policy correctly
even on the restricted runtime role.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "baseline_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("workload_id", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(length=16), nullable=False),
        sa.Column("bucket", sa.Integer(), nullable=False),
        sa.Column("center", sa.Float(), nullable=False),
        sa.Column("scale", sa.Float(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workload_id"], ["workloads.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "workload_id", "metric", "bucket", name="uq_baseline_wl_metric_bucket"
        ),
    )
    op.create_index(
        "ix_baseline_profiles_account_id", "baseline_profiles", ["account_id"]
    )
    op.create_index(
        "ix_baseline_profiles_workload_id", "baseline_profiles", ["workload_id"]
    )

    # Row-level security, mirroring the other tenant tables (see migration 0010).
    if is_pg:
        op.execute("ALTER TABLE baseline_profiles ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE baseline_profiles FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation ON baseline_profiles "
            "USING (account_id = "
            "NULLIF(current_setting('app.current_account', true), '')::int) "
            "WITH CHECK (account_id = "
            "NULLIF(current_setting('app.current_account', true), '')::int)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute(
            "DROP POLICY IF EXISTS tenant_isolation ON baseline_profiles"
        )
        op.execute("ALTER TABLE baseline_profiles NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE baseline_profiles DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_baseline_profiles_workload_id", table_name="baseline_profiles")
    op.drop_index("ix_baseline_profiles_account_id", table_name="baseline_profiles")
    op.drop_table("baseline_profiles")
