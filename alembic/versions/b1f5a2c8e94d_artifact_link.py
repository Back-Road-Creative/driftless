"""artifact_link: a URI reference filed against any record, not a file store

Revision ID: b1f5a2c8e94d
Revises: a1c4e6f8b2d3
Create Date: 2026-09-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1f5a2c8e94d"  # pragma: allowlist secret
down_revision: str | None = "a1c4e6f8b2d3"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artifact_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("record_kind", sa.String(length=100), nullable=False),
        sa.Column("record_id", sa.String(length=100), nullable=False),
        sa.Column("uri", sa.String(length=2000), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("row_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_artifact_link_record", "artifact_link", ["record_kind", "record_id"])


def downgrade() -> None:
    op.drop_table("artifact_link")
