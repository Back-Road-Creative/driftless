"""Add business-scoped project-to-objective contribution links.

Revision ID: f9b52e7d3a06
Revises: e8a41d6c2f95
Create Date: 2026-08-12 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f9b52e7d3a06"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "e8a41d6c2f95"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scorecard_contribution",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("objective_id", sa.Integer(), nullable=False),
        sa.Column("contribution_type", sa.String(length=20), nullable=False),
        sa.Column("rationale", sa.String(length=2000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "contribution_type IN ('direct', 'supporting')", name="ck_contribution_type"
        ),
        sa.CheckConstraint("status IN ('active', 'retired')", name="ck_status"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["objective_id"], ["strategic_objective.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "objective_id", name="uq_scorecard_contribution_project_objective"
        ),
    )
    op.create_index(
        "ix_scorecard_contribution_project_id", "scorecard_contribution", ["project_id"]
    )
    op.create_index(
        "ix_scorecard_contribution_objective_id", "scorecard_contribution", ["objective_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_scorecard_contribution_objective_id", table_name="scorecard_contribution")
    op.drop_index("ix_scorecard_contribution_project_id", table_name="scorecard_contribution")
    op.drop_table("scorecard_contribution")
