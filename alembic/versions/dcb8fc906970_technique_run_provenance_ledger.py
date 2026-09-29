"""technique_run: append-only provenance for every technique a project runs

Revision ID: dcb8fc906970
Revises: e2a91c4d70b8
Create Date: 2026-08-27 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "dcb8fc906970"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "e2a91c4d70b8"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Pinned literally, not read off the model — a migration is frozen history.
_METHODS = ("predictive", "scrum", "kanban", "department")


def upgrade() -> None:
    quoted = ", ".join(f"'{m}'" for m in _METHODS)
    op.create_table(
        "technique_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("technique_key", sa.String(length=100), nullable=False),
        sa.Column("process_id", sa.String(length=20), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("source_version", sa.String(length=200), nullable=False),
        sa.Column("inputs_snapshot", sa.Text(), nullable=False),
        sa.Column("outputs_produced", sa.Text(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"method IN ({quoted})", name="ck_method"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_technique_run_project_id", "technique_run", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_technique_run_project_id", table_name="technique_run")
    op.drop_table("technique_run")
