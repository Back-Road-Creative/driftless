"""api_token: per-user API credentials — one table off ``app_user``, reverses alone

Revision ID: a3f7c95d21e8
Revises: b46ef0a1c9d3
Create Date: 2026-07-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "a3f7c95d21e8"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "b46ef0a1c9d3"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_token",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),  # pragma: allowlist secret
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest"),  # pragma: allowlist secret
    )


def downgrade() -> None:
    op.drop_table("api_token")
