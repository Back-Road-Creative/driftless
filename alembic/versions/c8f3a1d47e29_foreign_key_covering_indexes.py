"""foreign keys: covering indexes

One index per foreign-key column that does not already lead a unique constraint — 23 of
them; without these every per-parent read ("the risks of THIS project") is a full SCAN of
the child table. Names follow SQLAlchemy's default ``ix_<table>_<column>`` — what
``index=True`` generates — because the parity suite compares the two schemas by name.

Revision ID: c8f3a1d47e29
Revises: b7d4e21f9c03
Create Date: 2026-07-30 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c8f3a1d47e29"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "b7d4e21f9c03"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Every foreign-key column with no unique constraint led by it, as (table, column).
_INDEXED: tuple[tuple[str, str], ...] = (
    ("api_token", "user_id"),
    ("baseline_line", "task_id"),
    ("change_request", "project_id"),
    ("change_request", "resulting_baseline_id"),
    ("cost_entry", "project_id"),
    ("issue", "project_id"),
    ("issue", "risk_id"),
    ("milestone", "project_id"),
    ("person", "department_id"),
    ("portfolio", "business_id"),
    ("procurement_agreement", "project_id"),
    ("program", "portfolio_id"),
    ("project", "portfolio_id"),
    ("project", "program_id"),
    ("project", "responsible_department_id"),
    ("quality_measurement", "project_id"),
    ("risk", "project_id"),
    ("sign_off", "project_id"),
    ("sprint", "project_id"),
    ("stakeholder", "project_id"),
    ("task", "assignee_id"),
    ("task", "workstream_id"),
    ("workstream", "project_id"),
)


def upgrade() -> None:
    for table, column in _INDEXED:
        op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table, column in reversed(_INDEXED):
        op.drop_index(f"ix_{table}_{column}", table_name=table)
