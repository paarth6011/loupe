"""per-account notification webhook url

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-14

Adds a per-tenant Slack/Discord webhook URL so each account can route its own
alert notifications, instead of the single global NOTIFY_WEBHOOK_URL env var.
Nullable: an account with no URL falls back to the global env (self-host) or no
notification at all (hosted, where the operator leaves the env empty). The
column lives on `accounts` (an auth-bootstrap table, not under RLS); the
notification endpoints scope it by the authenticated account in app code.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("notify_webhook_url", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("accounts", "notify_webhook_url")
