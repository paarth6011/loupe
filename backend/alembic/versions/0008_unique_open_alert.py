"""enforce one unresolved alert per (workload, rule)

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Resolve any pre-existing duplicate open alerts so the unique index can be
    # built: keep the most-recent open alert per (workload, rule), resolve the
    # rest. (Duplicates could exist from the pre-fix read-then-insert race.)
    op.execute(
        """
        UPDATE alerts SET resolved_at = now()
        WHERE resolved_at IS NULL
          AND id NOT IN (
              SELECT max(id) FROM alerts
              WHERE resolved_at IS NULL
              GROUP BY workload_id, rule
          )
        """
    )
    op.create_index(
        "uq_open_alert_per_rule",
        "alerts",
        ["workload_id", "rule"],
        unique=True,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_open_alert_per_rule", table_name="alerts")
