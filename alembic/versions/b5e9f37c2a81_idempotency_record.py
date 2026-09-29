"""idempotency_record: one row per spent Idempotency-Key

``key`` is UNIQUE and that constraint IS the mechanism. ``status_code``/
``response_body`` are nullable because the row is reserved BEFORE the request
runs, so a row with neither records an unknown outcome (``api.idempotency``).

Revision ID: b5e9f37c2a81
Revises: 4c96ce2fdaaf
Create Date: 2026-08-16 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5e9f37c2a81"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "4c96ce2fdaaf"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_idempotency_record_key"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_record")
