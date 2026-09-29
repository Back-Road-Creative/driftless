"""cost_entry: reversing corrections, not an edit

``CostEntry`` is append-only, so a wrong figure is corrected by a reversing
negative row plus a new correct row (see docs/temporal-model.md), never an
edit to the row a report has already been rendered from -- standard ledger
practice, and every as-of query then sums correctly with no flag a reader can
forget to filter on. ``ck_cost_entry_amount``'s old ``amount >= 0`` forbids
exactly that, so it is replaced with a symmetric sanity range instead of being
dropped outright: the old CHECK never caught a magnitude error (an extra
zero) anyway, only a sign, so the range keeps the protection actually being
provided while allowing the reversal. See ``driftless.models.records.
COST_ENTRY_AMOUNT_BOUND`` for how the bound was derived -- it is a judgement
call, not a fact about any organisation's finances.

``batch_alter_table`` is dialect-conditional (``alembic/env.py``): on SQLite
it is a copy-and-swap, on Postgres a plain ``ALTER TABLE ... DROP/ADD
CONSTRAINT``. Either way the downgrade below re-adds ``amount >= 0`` as a REAL
CHECK, which both dialects validate against every row already in the table
when it is added -- so if a reversal has already landed a negative ``amount``,
the downgrade itself fails loudly at that ALTER/copy with a constraint
violation, rather than silently leaving the store either under-protected or
claiming a guarantee that does not hold. There is deliberately no Python-level
guard duplicating that check: the constraint IS the check.

Revision ID: cd96d900768b
Revises: ff230d5c1eb0
Create Date: 2026-08-15 11:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "cd96d900768b"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "ff230d5c1eb0"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must equal driftless.models.records.COST_ENTRY_AMOUNT_BOUND, cast the same way -- migrations
# hardcode their own SQL rather than import application code (see every prior revision), and
# tests/test_migrations.py's create_all-vs-migrated CHECK-text parity check is what catches the
# two ever drifting apart.
_RANGE = "amount BETWEEN -30000000 AND 30000000"
_NONNEGATIVE = "amount >= 0"


def upgrade() -> None:
    with op.batch_alter_table("cost_entry", schema=None) as batch_op:
        batch_op.drop_constraint("ck_cost_entry_amount", type_="check")
        batch_op.create_check_constraint("ck_cost_entry_amount", _RANGE)


def downgrade() -> None:
    with op.batch_alter_table("cost_entry", schema=None) as batch_op:
        batch_op.drop_constraint("ck_cost_entry_amount", type_="check")
        batch_op.create_check_constraint("ck_cost_entry_amount", _NONNEGATIVE)
