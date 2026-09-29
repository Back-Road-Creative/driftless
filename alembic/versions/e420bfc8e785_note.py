"""note: an append-only note filed against any record

Revision ID: e420bfc8e785
Revises: b1f5a2c8e94d
Create Date: 2026-09-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e420bfc8e785"  # pragma: allowlist secret
down_revision: str | None = "b1f5a2c8e94d"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "note",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("record_kind", sa.String(length=100), nullable=False),
        sa.Column("record_id", sa.String(length=100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("supersedes_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["supersedes_id"], ["note.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_note_record", "note", ["record_kind", "record_id"])
    op.create_index("ix_note_supersedes_id", "note", ["supersedes_id"])


def downgrade() -> None:
    op.drop_index("ix_note_supersedes_id", table_name="note")
    op.drop_index("ix_note_record", table_name="note")
    op.drop_table("note")
