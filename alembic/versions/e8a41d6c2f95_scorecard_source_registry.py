"""Add governed business-scoped scorecard sources.

Revision ID: e8a41d6c2f95
Revises: d7f29c5a1e84
Create Date: 2026-08-12 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8a41d6c2f95"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "d7f29c5a1e84"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scorecard_source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.CheckConstraint("status IN ('active', 'retired')", name="ck_status"),
        sa.ForeignKeyConstraint(["business_id"], ["business.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "key", name="uq_scorecard_source_business_key"),
    )
    op.create_index("ix_scorecard_source_business_id", "scorecard_source", ["business_id"])


def downgrade() -> None:
    op.drop_index("ix_scorecard_source_business_id", table_name="scorecard_source")
    op.drop_table("scorecard_source")
