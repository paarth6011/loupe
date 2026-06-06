"""add severity and summary to alerts

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "alerts",
        sa.Column(
            "severity",
            sa.String(length=16),
            nullable=False,
            server_default="warning",  # backfill existing rows
        ),
    )
    op.add_column("alerts", sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("alerts", "summary")
    op.drop_column("alerts", "severity")
