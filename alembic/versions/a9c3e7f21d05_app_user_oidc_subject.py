"""app_user: oidc_subject

One nullable, unique column on ``app_user``, binding a login to an external IdP's
``sub`` for OIDC sign-in (``driftless.auth.oidc``). Bound only by an admin, through
``driftless user oidc-subject`` — never written by the sign-in flow itself, which
only reads it back to find the local account a ``sub`` maps to.

Revision ID: a9c3e7f21d05
Revises: 7642894637a8
Create Date: 2026-09-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9c3e7f21d05"  # pragma: allowlist secret
down_revision: str | None = "7642894637a8"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Batch mode: SQLite cannot ALTER a table to add a named constraint directly
    # (alembic.ddl.sqlite.SQLiteImpl.add_constraint refuses it), only recreate the
    # table via the copy-and-move strategy batch mode drives. Postgres/MySQL run
    # this as plain ALTER statements either way.
    # Named to match the model's ``UniqueConstraint(..., name="uq_app_user_oidc_subject")``
    # in ``__table_args__`` — batch mode recreates the table via reflection and
    # requires every constraint to carry a name, and the migration test compares
    # migrated DDL against ``create_all`` byte-for-byte, constraint names included.
    with op.batch_alter_table("app_user") as batch_op:
        batch_op.add_column(sa.Column("oidc_subject", sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint("uq_app_user_oidc_subject", ["oidc_subject"])


def downgrade() -> None:
    # Batch mode recreates the table from the reflected columns minus this one, so
    # the (unnamed) unique constraint drops with it — nothing else to undo.
    with op.batch_alter_table("app_user") as batch_op:
        batch_op.drop_column("oidc_subject")
