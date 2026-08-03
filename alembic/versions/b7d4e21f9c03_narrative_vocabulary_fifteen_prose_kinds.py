"""narrative_artifact: the kind vocabulary learns the fifteen prose kinds

Widens the ``ck_kind`` CHECK so the store accepts the subsidiary management plans,
statements and assessments under their catalog artifact names. No data moves and no
column changes; existing rows all use the original four kinds, so upgrade and
downgrade are both safe on any real store. SQLite cannot alter a CHECK in place —
batch mode rebuilds the table copy-and-move (Postgres alters in place).

Both vocabularies are pinned literally rather than imported from the model: a
migration is frozen history, and reading the live tuple would let a later widening
silently rewrite what this revision builds. Parity with the model is proved at head
by ``tests/test_migrations.py``, not here.

Revision ID: b7d4e21f9c03
Revises: e5c2a94d7b18
Create Date: 2026-07-30 18:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7d4e21f9c03"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "e5c2a94d7b18"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The vocabulary before this revision — the downgrade target.
_ORIGINAL = ("assumption_log", "eef", "opa", "lessons_learned")

#: The widened vocabulary this revision builds: the legacy four, then the fifteen
#: prose kinds stored under their catalog artifact names.
_WIDENED = _ORIGINAL + (
    "scope_management_plan",
    "requirements_management_plan",
    "schedule_management_plan",
    "cost_management_plan",
    "quality_management_plan",
    "resource_management_plan",
    "communications_management_plan",
    "risk_management_plan",
    "procurement_management_plan",
    "stakeholder_engagement_plan",
    "project_scope_statement",
    "requirements_documentation",
    "team_charter",
    "basis_of_estimates",
    "team_performance_assessments",
)


def _check_sql(kinds: Sequence[str]) -> str:
    quoted = ", ".join(f"'{kind}'" for kind in kinds)
    return f"kind IN ({quoted})"


def upgrade() -> None:
    with op.batch_alter_table("narrative_artifact", schema=None) as batch_op:
        batch_op.drop_constraint("ck_kind", type_="check")
        batch_op.create_check_constraint("ck_kind", _check_sql(_WIDENED))


def downgrade() -> None:
    with op.batch_alter_table("narrative_artifact", schema=None) as batch_op:
        batch_op.drop_constraint("ck_kind", type_="check")
        batch_op.create_check_constraint("ck_kind", _check_sql(_ORIGINAL))
