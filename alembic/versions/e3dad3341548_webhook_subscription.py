"""webhook_subscription: one row per subscriber, cursored off change_log

Revision ID: e3dad3341548
Revises: e7a3c95f2d41
Create Date: 2026-09-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3dad3341548"  # pragma: allowlist secret
down_revision: str | None = "e7a3c95f2d41"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK = "url LIKE 'https://%' OR url LIKE 'http://127.0.0.1%' OR url LIKE 'http://localhost%'"


def upgrade() -> None:
    op.create_table(
        "webhook_subscription",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("secret", sa.String(length=500), nullable=False),
        sa.Column("events", sa.Text(), nullable=False),
        sa.Column("last_delivered_changelog_id", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_CHECK, name="ck_webhook_subscription_https"),
    )


def downgrade() -> None:
    op.drop_table("webhook_subscription")
