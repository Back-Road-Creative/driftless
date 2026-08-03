"""app_user: stored identity

One table, ``app_user`` (``user`` is reserved in Postgres); nothing existing
changes, so it reverses alone. Proven against the models by the migration test.

Revision ID: c3d81f60ab27
Revises: f4a9c2e17b30
Create Date: 2026-07-24 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "c3d81f60ab27"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "f4a9c2e17b30"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'contributor', 'viewer')", name="ck_role"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )


def downgrade() -> None:
    op.drop_table("app_user")
