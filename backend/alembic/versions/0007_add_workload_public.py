"""add public flag to workloads for the status page

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Default false: existing workloads stay private until explicitly published.
    op.add_column(
        "workloads",
        sa.Column(
            "public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("workloads", "public")
