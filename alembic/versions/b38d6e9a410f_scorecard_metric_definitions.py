"""Add directional, objective-owned scorecard metric definitions.

Revision ID: b38d6e9a410f
Revises: af4e7b12c9d1
Create Date: 2026-08-12 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b38d6e9a410f"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "af4e7b12c9d1"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scorecard_metric_definition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("objective_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("amber_threshold", sa.Float(), nullable=False),
        sa.Column("red_threshold", sa.Float(), nullable=False),
        sa.Column("cadence_days", sa.Integer(), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_key", sa.String(length=100), nullable=True),
        sa.CheckConstraint(
            "direction IN ('higher_is_better', 'lower_is_better')", name="ck_direction"
        ),
        sa.CheckConstraint(
            "source_type IN ('manual', 'registered_connector')", name="ck_source_type"
        ),
        sa.CheckConstraint("cadence_days > 0", name="ck_scorecard_metric_cadence"),
        sa.CheckConstraint(
            "(direction = 'higher_is_better' AND target_value >= amber_threshold AND amber_threshold >= red_threshold) OR "
            "(direction = 'lower_is_better' AND target_value <= amber_threshold AND amber_threshold <= red_threshold)",
            name="ck_scorecard_metric_directional_thresholds",
        ),
        sa.CheckConstraint(
            "(source_type = 'manual' AND source_key IS NULL) OR "
            "(source_type = 'registered_connector' AND source_key IS NOT NULL)",
            name="ck_scorecard_metric_source_key",
        ),
        sa.ForeignKeyConstraint(["objective_id"], ["strategic_objective.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("objective_id", "name", name="uq_scorecard_metric_objective_name"),
    )
    op.create_index(
        "ix_scorecard_metric_definition_objective_id",
        "scorecard_metric_definition",
        ["objective_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scorecard_metric_definition_objective_id", table_name="scorecard_metric_definition"
    )
    op.drop_table("scorecard_metric_definition")
