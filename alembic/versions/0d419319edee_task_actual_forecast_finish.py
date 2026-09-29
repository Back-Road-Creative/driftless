"""task: actual and forecast finish dates

Two nullable columns the DCMA schedule-health checks (invalid dates, missed tasks,
BEI) read off a task — ``actual_finish``/``forecast_finish`` mappings the model had
nowhere to record before this, so those checks reported "not assessable" for every
task. Both nullable and no backfill: a task nobody has dated either way stays
unassessable, which is the honest state, not an invented one.

Revision ID: 0d419319edee
Revises: e420bfc8e785
Create Date: 2026-09-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0d419319edee"  # pragma: allowlist secret
down_revision: str | None = "e420bfc8e785"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("task", sa.Column("actual_finish", sa.Date(), nullable=True))
    op.add_column("task", sa.Column("forecast_finish", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("task", "forecast_finish")
    op.drop_column("task", "actual_finish")
