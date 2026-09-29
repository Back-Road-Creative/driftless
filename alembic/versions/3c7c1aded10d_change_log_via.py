"""change_log: via

One nullable column: the channel a write came through
(``driftless.db.changelog.CHANGE_CHANNELS`` — ``web``, ``api``, ``cli``, ``mcp``). A NULL
CHECK evaluates to unknown, which passes, so the same ``ck_via`` constraint the model
builds with ``one_of`` covers every existing row without a backfill — old rows keep
``via=None``, read as "unknown", exactly as an unattributed ``actor`` already is.

Revision ID: 3c7c1aded10d
Revises: ca6fe294b54a
Create Date: 2026-09-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3c7c1aded10d"  # pragma: allowlist secret
down_revision: str | None = "ca6fe294b54a"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Pinned literally rather than imported: a migration is frozen history, and reading the
#: live tuple would let a later widening silently rewrite what this revision builds.
_CHANNELS = ("web", "api", "cli", "mcp")


def upgrade() -> None:
    with op.batch_alter_table("change_log", schema=None) as batch_op:
        batch_op.add_column(sa.Column("via", sa.String(length=20), nullable=True))
        quoted = ", ".join(f"'{channel}'" for channel in _CHANNELS)
        batch_op.create_check_constraint("ck_via", f"via IN ({quoted})")


def downgrade() -> None:
    with op.batch_alter_table("change_log", schema=None) as batch_op:
        batch_op.drop_constraint("ck_via", type_="check")
        batch_op.drop_column("via")
