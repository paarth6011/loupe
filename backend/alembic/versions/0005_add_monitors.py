"""add monitors table for per-workload rule config

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monitors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workload_id", sa.Integer(), nullable=False),
        sa.Column("rule", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workload_id"], ["workloads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workload_id", "rule", name="uq_monitor_rule"),
    )
    op.create_index(
        op.f("ix_monitors_workload_id"), "monitors", ["workload_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_monitors_workload_id"), table_name="monitors")
    op.drop_table("monitors")
