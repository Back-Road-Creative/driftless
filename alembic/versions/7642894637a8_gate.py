"""Add gate: a stage boundary, and sign_off learns "gate" as a subject.

``gate`` is a thin definition row (plan gap G20) — name, sequence ``position``,
and ``required_processes`` (a comma-separated list of PMBOK clause numbers).
Readiness and passage are both computed, never stored, so this migration adds
no status column: passage is recorded as a ``sign_off`` row, which is why
``ck_subject_kind`` widens alongside the new table. SQLite cannot alter a CHECK
in place — batch mode rebuilds the table copy-and-move (Postgres alters in
place), the same shape ``452898b6df2a`` already uses.

Both vocabularies are pinned literally rather than imported from the model —
see that revision's own docstring for why. Parity with the model is proved at
head by ``tests/test_migrations.py``, not here.

Revision ID: 7642894637a8
Revises: 452898b6df2a
Create Date: 2026-09-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7642894637a8"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "452898b6df2a"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The vocabulary before this revision — the downgrade target.
_ORIGINAL = ("threat", "process", "baseline")

#: The widened vocabulary this revision builds.
_WIDENED = _ORIGINAL + ("gate",)


def _check_sql(kinds: Sequence[str]) -> str:
    quoted = ", ".join(f"'{kind}'" for kind in kinds)
    return f"subject_kind IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "gate",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("required_processes", sa.String(length=2000), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gate_project_id", "gate", ["project_id"])
    with op.batch_alter_table("sign_off", schema=None) as batch_op:
        batch_op.drop_constraint("ck_subject_kind", type_="check")
        batch_op.create_check_constraint("ck_subject_kind", _check_sql(_WIDENED))


def downgrade() -> None:
    with op.batch_alter_table("sign_off", schema=None) as batch_op:
        batch_op.drop_constraint("ck_subject_kind", type_="check")
        batch_op.create_check_constraint("ck_subject_kind", _check_sql(_ORIGINAL))
    op.drop_index("ix_gate_project_id", table_name="gate")
    op.drop_table("gate")
