"""add detector column to alerts

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing alerts were all threshold-based; backfill them via server_default.
    op.add_column(
        "alerts",
        sa.Column(
            "detector",
            sa.String(length=16),
            nullable=False,
            server_default="threshold",
        ),
    )


def downgrade() -> None:
    op.drop_column("alerts", "detector")
