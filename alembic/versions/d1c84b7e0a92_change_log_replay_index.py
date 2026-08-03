"""change_log: an index for the progress replay — additive, reverses alone

One index on an existing table. No column moves, nothing is backfilled and no row is
rewritten, so every row that already exists is valid the instant the index appears.
``assess.adapters.progress_history`` reads the log by identity — ``table_name`` and
``row_id`` equal, ``changed_at`` the order the readings are replayed in — and until now
had nothing behind that filter, so the planner read the whole log to answer one project.

Revision ID: d1c84b7e0a92
Revises: a3f7c95d21e8
Create Date: 2026-07-30 09:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


revision: str = "d1c84b7e0a92"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "a3f7c95d21e8"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_change_log_table_row_changed",
        "change_log",
        ["table_name", "row_id", "changed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_change_log_table_row_changed", table_name="change_log")
