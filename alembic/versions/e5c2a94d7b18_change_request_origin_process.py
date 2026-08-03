"""change_request: origin process provenance — additive, reverses alone

One nullable column on ``change_request``: the PMBOK clause id of the process that
raised the request, captured from the surfaces that know it (the wizard step, the
CLI's ``--process`` flag). Nullable with no backfill because history genuinely does
not know — every row that already exists is valid the instant the column appears.

Revision ID: e5c2a94d7b18
Revises: d1c84b7e0a92
Create Date: 2026-07-30 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "e5c2a94d7b18"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "d1c84b7e0a92"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "change_request",
        sa.Column("origin_process_id", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("change_request", "origin_process_id")
