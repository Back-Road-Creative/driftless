"""app_user: session epoch

One column on ``app_user``. A server default of ``0`` rather than a backfill, so
every row that already exists is valid the instant the column appears and the
migration needs no data step; reverses alone.

Revision ID: b46ef0a1c9d3
Revises: c3d81f60ab27
Create Date: 2026-07-25 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "b46ef0a1c9d3"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "c3d81f60ab27"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("app_user", "session_epoch")
