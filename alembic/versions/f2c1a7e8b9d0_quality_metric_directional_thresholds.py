"""quality: project metric definitions and optional measurement links

Quality readings used to carry an implicit comparison direction. This adds a
reusable project-level definition with explicit matching threshold(s). The new
link is nullable, so an upgrade preserves historical evidence unchanged.

Revision ID: f2c1a7e8b9d0
Revises: c8f3a1d47e29
Create Date: 2026-08-12 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c1a7e8b9d0"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "c8f3a1d47e29"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quality_metric",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("lower_bound", sa.Float(), nullable=True),
        sa.Column("upper_bound", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.CheckConstraint(
            "direction IN ('lower_is_better', 'higher_is_better', 'target_band')",
            name="ck_direction",
        ),
        sa.CheckConstraint(
            "(direction = 'lower_is_better' AND lower_bound IS NULL AND upper_bound IS NOT NULL) "
            "OR (direction = 'higher_is_better' AND lower_bound IS NOT NULL "
            "AND upper_bound IS NULL) "
            "OR (direction = 'target_band' AND lower_bound IS NOT NULL AND upper_bound IS NOT NULL "
            "AND lower_bound <= upper_bound)",
            name="ck_quality_metric_directional_bounds",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_quality_metric_project_name"),
    )
    op.create_index("ix_quality_metric_project_id", "quality_metric", ["project_id"])
    with op.batch_alter_table("quality_measurement", schema=None) as batch_op:
        batch_op.add_column(sa.Column("quality_metric_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_quality_measurement_quality_metric",
            "quality_metric",
            ["quality_metric_id"],
            ["id"],
        )
    op.create_index(
        "ix_quality_measurement_quality_metric_id",
        "quality_measurement",
        ["quality_metric_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_quality_measurement_quality_metric_id", table_name="quality_measurement")
    with op.batch_alter_table("quality_measurement", schema=None) as batch_op:
        batch_op.drop_constraint("fk_quality_measurement_quality_metric", type_="foreignkey")
        batch_op.drop_column("quality_metric_id")
    op.drop_index("ix_quality_metric_project_id", table_name="quality_metric")
    op.drop_table("quality_metric")
