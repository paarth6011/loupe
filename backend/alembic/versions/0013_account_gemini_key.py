"""per-account gemini api key for incident summaries

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-24

Adds a per-tenant Gemini API key (BYOK) used only for LLM incident summaries,
so each account brings its own free key instead of the operator paying for
everyone's summaries with a single global key. Nullable: an account with no key
falls back to the global GEMINI_API_KEY env (self-host) or the $0 template
summarizer (hosted, where the operator leaves the env empty). The column lives
on `accounts` (an auth-bootstrap table, not under RLS); the summarizer endpoints
scope it by the authenticated account in app code.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("gemini_api_key", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("accounts", "gemini_api_key")
