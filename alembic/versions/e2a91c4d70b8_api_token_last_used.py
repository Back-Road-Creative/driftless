"""api_token: last use

One nullable column on ``api_token``. ``NULL`` means "never seen used" — true both of
a token nobody has spent and of every token minted before this column existed, so no
backfill and no server default; reverses alone. A stamp is not an audited write and
carries no actor, so nothing about ``change_log`` moves with it.

Revision ID: e2a91c4d70b8
Revises: b5e9f37c2a81
Create Date: 2026-08-16 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2a91c4d70b8"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "b5e9f37c2a81"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_token",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_token", "last_used_at")
