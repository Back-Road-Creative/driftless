"""email_subscription: a user's periodic attention-list digest, cursored by as-of

Revision ID: a1c4e6f8b2d3
Revises: e3dad3341548
Create Date: 2026-09-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e6f8b2d3"  # pragma: allowlist secret
down_revision: str | None = "e3dad3341548"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CADENCES = ("daily", "weekly", "monthly")
_CHECK = "cadence IN ({})".format(", ".join(f"'{c}'" for c in _CADENCES))


def upgrade() -> None:
    op.create_table(
        "email_subscription",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("cadence", sa.String(length=20), nullable=False),
        sa.Column("last_sent_as_of", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_CHECK, name="ck_cadence"),
    )
    op.create_index("ix_email_subscription_user_id", "email_subscription", ["user_id"])


def downgrade() -> None:
    op.drop_table("email_subscription")
