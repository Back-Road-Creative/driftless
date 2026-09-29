"""Add append-only scorecard metric observations.

Revision ID: d7f29c5a1e84
Revises: b38d6e9a410f
Create Date: 2026-08-12 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7f29c5a1e84"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "b38d6e9a410f"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scorecard_metric_observation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_definition_id", sa.Integer(), nullable=False),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("evidence_note", sa.String(length=2000), nullable=False),
        sa.ForeignKeyConstraint(["metric_definition_id"], ["scorecard_metric_definition.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scorecard_metric_observation_metric_definition_id",
        "scorecard_metric_observation",
        ["metric_definition_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scorecard_metric_observation_metric_definition_id",
        table_name="scorecard_metric_observation",
    )
    op.drop_table("scorecard_metric_observation")
