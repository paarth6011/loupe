"""add LLM fields to metric_samples

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "metric_samples", sa.Column("model", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "metric_samples", sa.Column("provider", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "metric_samples", sa.Column("input_tokens", sa.Integer(), nullable=True)
    )
    op.add_column(
        "metric_samples", sa.Column("output_tokens", sa.Integer(), nullable=True)
    )
    op.add_column("metric_samples", sa.Column("cost_usd", sa.Float(), nullable=True))
    op.add_column(
        "metric_samples", sa.Column("operation", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "metric_samples", sa.Column("error_type", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    for col in (
        "error_type",
        "operation",
        "cost_usd",
        "output_tokens",
        "input_tokens",
        "provider",
        "model",
    ):
        op.drop_column("metric_samples", col)
