"""lesson_learned: one row per lesson raised, replacing prose-only knowledge

Revision ID: a4e19c7f2b83
Revises: 6c2ec0e6d92d
Create Date: 2026-08-27 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4e19c7f2b83"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "6c2ec0e6d92d"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Pinned literally, not read off the model — a migration is frozen history.
_CATEGORIES = (
    "integration",
    "scope",
    "schedule",
    "cost",
    "quality",
    "resource",
    "communications",
    "risk",
    "procurement",
    "stakeholder",
)


def upgrade() -> None:
    quoted = ", ".join(f"'{c}'" for c in _CATEGORIES)
    op.create_table(
        "lesson_learned",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("raised_on", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("what_happened", sa.Text(), nullable=False),
        sa.Column("what_to_do_next_time", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(f"category IN ({quoted})", name="ck_category"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lesson_learned_project_id", "lesson_learned", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_lesson_learned_project_id", table_name="lesson_learned")
    op.drop_table("lesson_learned")
