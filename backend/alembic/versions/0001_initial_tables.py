"""initial tables: workloads, metric_samples, alerts

Revision ID: 0001
Revises:
Create Date: 2026-06-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workloads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_workloads_name", "workloads", ["name"], unique=True)

    op.create_table(
        "metric_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workload_id",
            sa.Integer(),
            sa.ForeignKey("workloads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=True),
    )
    op.create_index("ix_metric_samples_workload_id", "metric_samples", ["workload_id"])
    op.create_index("ix_metric_samples_ts", "metric_samples", ["ts"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workload_id",
            sa.Integer(),
            sa.ForeignKey("workloads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule", sa.String(length=64), nullable=False),
        sa.Column("message", sa.String(length=512), nullable=False),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alerts_workload_id", "alerts", ["workload_id"])


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("metric_samples")
    op.drop_table("workloads")
