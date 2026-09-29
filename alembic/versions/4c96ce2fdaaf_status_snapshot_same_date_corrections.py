"""status_snapshot: same-date corrections accepted, latest recorded wins

``uq_status_snapshot_project_date`` made a second row for an already-
snapshotted date an ``IntegrityError``, leaving an append-only table with no
way to correct a wrong reading at all. See ``docs/temporal-model.md`` and
``driftless.models.records.StatusSnapshot`` for the decision this drops it
for: the second filing is now accepted, and the most recently RECORDED row
answers every "latest reading" read.

``batch_alter_table`` is dialect-conditional (``alembic/env.py``): SQLite
copy-and-swaps, Postgres alters in place. Either way the downgrade re-adds the
unique constraint for real, which both dialects validate against every
existing row -- so if a same-date correction has already landed, the
downgrade fails loudly at that ALTER/copy with a uniqueness violation, rather
than silently discarding a row or claiming a guarantee the store no longer
holds. No Python-level guard duplicates that check: the constraint IS it.

Revision ID: 4c96ce2fdaaf
Revises: cd96d900768b
Create Date: 2026-08-16 09:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "4c96ce2fdaaf"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "cd96d900768b"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("status_snapshot", schema=None) as batch_op:
        batch_op.drop_constraint("uq_status_snapshot_project_date", type_="unique")
        # ``project_id`` LED the constraint being dropped, so it inherited that index for
        # free, and every "this project's series" read rode on it. Dropping the constraint
        # without this would leave the busiest foreign key on the table unindexed -- a
        # silent performance regression, not a correctness one, which is exactly the kind
        # that survives a green suite. ``tests/test_db_hardening.py`` refuses it.
        batch_op.create_index("ix_status_snapshot_project_id", ["project_id"])


def downgrade() -> None:
    with op.batch_alter_table("status_snapshot", schema=None) as batch_op:
        batch_op.drop_index("ix_status_snapshot_project_id")
        batch_op.create_unique_constraint(
            "uq_status_snapshot_project_date", ["project_id", "taken_on"]
        )
