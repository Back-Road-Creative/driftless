"""api_token: expiry

One nullable column on ``api_token``. ``NULL`` means "never expires" — the only
value every token minted before this column existed can honestly carry, so no
backfill and no server default; reverses alone.

Revision ID: ff230d5c1eb0
Revises: c19e3eff4b27
Create Date: 2026-08-14 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ff230d5c1eb0"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "c19e3eff4b27"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_token",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_token", "expires_at")
