"""scorecard: versioned metric definitions, not mutable thresholds

Pre-existing rows backfill to ``METRIC_ALWAYS`` (``date.min``), NOT NULL: domain
rows carry no ``created_at`` for an honest start. A VALUE, not NULL -- the
constraint widens to include it and SQL holds no two NULLs equal, so nullable
would let one objective carry unlimited metrics of one name; SQLite cannot ALTER
a UNIQUE constraint, hence the batch rebuild.

Revision ID: c19e3eff4b27
Revises: 7cbe3c7ed36e
Create Date: 2026-08-13 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c19e3eff4b27"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "7cbe3c7ed36e"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scorecard_metric_definition", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("effective_from", sa.Date(), nullable=False, server_default="0001-01-01")
        )
        batch_op.drop_constraint("uq_scorecard_metric_objective_name", type_="unique")
        batch_op.create_unique_constraint(
            "uq_scorecard_metric_objective_name",
            ["objective_id", "name", "effective_from"],
        )


def downgrade() -> None:
    with op.batch_alter_table("scorecard_metric_definition", schema=None) as batch_op:
        batch_op.drop_constraint("uq_scorecard_metric_objective_name", type_="unique")
        batch_op.create_unique_constraint(
            "uq_scorecard_metric_objective_name", ["objective_id", "name"]
        )
        batch_op.drop_column("effective_from")
