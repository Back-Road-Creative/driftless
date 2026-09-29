"""sign_off: subject_kind vocabulary learns "baseline"

Widens ``ck_subject_kind`` on ``sign_off`` so a decision can reference a
``Baseline`` version, alongside the existing ``"threat"`` and ``"process"``
subjects. No data moves and no column changes; existing rows all use the
original two kinds, so upgrade and downgrade are both safe on any real store.
SQLite cannot alter a CHECK in place — batch mode rebuilds the table
copy-and-move (Postgres alters in place).

Both vocabularies are pinned literally rather than imported from the model: a
migration is frozen history, and reading the live tuple would let a later
widening silently rewrite what this revision builds. Parity with the model is
proved at head by ``tests/test_migrations.py``, not here.

Revision ID: 452898b6df2a
Revises: 7b8f97e1c973
Create Date: 2026-09-23 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "452898b6df2a"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "7b8f97e1c973"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The vocabulary before this revision — the downgrade target.
_ORIGINAL = ("threat", "process")

#: The widened vocabulary this revision builds.
_WIDENED = _ORIGINAL + ("baseline",)


def _check_sql(kinds: Sequence[str]) -> str:
    quoted = ", ".join(f"'{kind}'" for kind in kinds)
    return f"subject_kind IN ({quoted})"


def upgrade() -> None:
    with op.batch_alter_table("sign_off", schema=None) as batch_op:
        batch_op.drop_constraint("ck_subject_kind", type_="check")
        batch_op.create_check_constraint("ck_subject_kind", _check_sql(_WIDENED))


def downgrade() -> None:
    with op.batch_alter_table("sign_off", schema=None) as batch_op:
        batch_op.drop_constraint("ck_subject_kind", type_="check")
        batch_op.create_check_constraint("ck_subject_kind", _check_sql(_ORIGINAL))
