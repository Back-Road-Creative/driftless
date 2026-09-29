"""project: delivery_mode learns operations, department-cadence work

Widens the ``ck_delivery_mode`` CHECK so a project can be tailored to
``ControlMode.OPERATIONS_CADENCE`` (``driftless.pmbok.tailoring``) — a
project whose Monitoring & Controlling reading is department service-level
and incident evidence rather than a baseline or a sprint commitment. No data
moves and no column changes; existing rows all use the original three modes,
so upgrade and downgrade are both safe on any real store. SQLite cannot alter
a CHECK in place — batch mode rebuilds the table copy-and-move (Postgres
alters in place).

Both vocabularies are pinned literally rather than imported from the model:
a migration is frozen history, and reading the live tuple would let a later
widening silently rewrite what this revision builds. Parity with the model is
proved at head by ``tests/test_migrations.py``, not here.

Revision ID: d4f8b3e19a72
Revises: a4e19c7f2b83
Create Date: 2026-08-27 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d4f8b3e19a72"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "a4e19c7f2b83"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The vocabulary before this revision — the downgrade target.
_ORIGINAL = ("predictive", "agile", "hybrid")

#: The widened vocabulary this revision builds.
_WIDENED = _ORIGINAL + ("operations",)


def _check_sql(modes: Sequence[str]) -> str:
    quoted = ", ".join(f"'{mode}'" for mode in modes)
    return f"delivery_mode IN ({quoted})"


def upgrade() -> None:
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.drop_constraint("ck_delivery_mode", type_="check")
        batch_op.create_check_constraint("ck_delivery_mode", _check_sql(_WIDENED))


def downgrade() -> None:
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.drop_constraint("ck_delivery_mode", type_="check")
        batch_op.create_check_constraint("ck_delivery_mode", _check_sql(_ORIGINAL))
