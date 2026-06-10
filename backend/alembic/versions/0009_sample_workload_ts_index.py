"""composite index on metric_samples(workload_id, ts)

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-10

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Window/aggregation queries filter workload_id AND ts >= start; a composite
    # index serves them far better than the two single-column indexes alone.
    op.create_index(
        "ix_samples_workload_ts",
        "metric_samples",
        ["workload_id", "ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_samples_workload_ts", table_name="metric_samples")
