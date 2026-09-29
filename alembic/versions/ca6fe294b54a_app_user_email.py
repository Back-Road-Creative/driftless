"""app_user: email

One nullable column on ``app_user``. Optional and unvalidated at the storage
layer — the CLI (``driftless.auth.cli``) is the one write path and validates
shape before a row is ever written, so no CHECK is added here. The digest
(``driftless.notify.digest``) prefers it over ``username`` and falls back to an
``@``-shaped username only when it is unset.

Revision ID: ca6fe294b54a
Revises: 0d419319edee
Create Date: 2026-09-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ca6fe294b54a"  # pragma: allowlist secret
down_revision: str | None = "0d419319edee"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("email", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("app_user", "email")
