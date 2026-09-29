"""Add business-scoped strategic objectives for the balanced scorecard.

Revision ID: af4e7b12c9d1
Revises: f2c1a7e8b9d0
Create Date: 2026-08-12 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "af4e7b12c9d1"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "f2c1a7e8b9d0"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategic_objective",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("perspective", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("active_from", sa.Date(), nullable=True),
        sa.Column("active_until", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "perspective IN ('financial', 'customer_stakeholder', 'internal_operations', "
            "'people_capability')",
            name="ck_perspective",
        ),
        sa.CheckConstraint("status IN ('active', 'paused', 'retired')", name="ck_status"),
        sa.CheckConstraint(
            "active_until IS NULL OR active_from IS NULL OR active_from <= active_until",
            name="ck_strategic_objective_active_window",
        ),
        sa.ForeignKeyConstraint(["business_id"], ["business.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "name", name="uq_strategic_objective_business_name"),
    )
    op.create_index("ix_strategic_objective_business_id", "strategic_objective", ["business_id"])


def downgrade() -> None:
    op.drop_index("ix_strategic_objective_business_id", table_name="strategic_objective")
    op.drop_table("strategic_objective")
