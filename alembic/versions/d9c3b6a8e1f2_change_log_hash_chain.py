"""change_log: tamper-evident hash chain

Two columns: ``prev_hash``, the previous row's ``row_hash`` (or a fixed genesis value for
the first row), and ``row_hash``, sha256 of ``prev_hash`` concatenated with this row's own
canonical content. Editing or deleting any row — the last one included, which an
edit-in-place attacker would otherwise leave with nothing pointing at it — breaks the link
the next row, or a re-walk of the whole table, expects. ``driftless.db.changelog.verify_chain``
is the read side of this proof.

Both columns land ``NOT NULL``: existing rows are backfilled here, in id order, before the
constraint is added, so an upgraded store verifies intact the moment this migration finishes.
The hashing logic is reproduced rather than imported — a migration is frozen history, and
importing the live implementation would let a later change to it silently rewrite what this
revision computed.

Revision ID: d9c3b6a8e1f2
Revises: 3c7c1aded10d
Create Date: 2026-09-23 00:00:00.000000

"""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "d9c3b6a8e1f2"  # pragma: allowlist secret
down_revision: str | None = "3c7c1aded10d"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Pinned literally, matching ``driftless.db.changelog.GENESIS_HASH`` as it stood when this
#: revision was written.
_GENESIS_HASH = "0" * 64
_CONTENT_FIELDS = ("table_name", "row_id", "operation", "changed_at", "actor", "via", "detail")

_LOGGED = sa.text(
    "SELECT id, table_name, row_id, operation, changed_at, actor, via, detail"
    " FROM change_log ORDER BY id"
).columns(changed_at=sa.DateTime(timezone=True))
_CHANGE_LOG = sa.table(
    "change_log",
    sa.column("id", sa.Integer),
    sa.column("prev_hash", sa.String),
    sa.column("row_hash", sa.String),
)


def _canonical_timestamp(changed_at: datetime) -> str:
    if changed_at.tzinfo is not None:
        changed_at = changed_at.astimezone(UTC).replace(tzinfo=None)
    return changed_at.isoformat()


def _content(
    table_name: str,
    row_id: str,
    operation: str,
    changed_at: datetime,
    actor: str | None,
    via: str | None,
    detail: str,
) -> dict[str, Any]:
    values = (table_name, row_id, operation, _canonical_timestamp(changed_at), actor, via, detail)
    return dict(zip(_CONTENT_FIELDS, values, strict=True))


def _row_hash(prev_hash: str, content: dict[str, Any]) -> str:
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


def upgrade() -> None:
    with op.batch_alter_table("change_log", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prev_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("row_hash", sa.String(length=64), nullable=True))

    bind = op.get_bind()
    prev_hash = _GENESIS_HASH
    for row_id, table_name, log_row_id, operation, changed_at, actor, via, detail in bind.execute(
        _LOGGED
    ).all():
        content = _content(table_name, log_row_id, operation, changed_at, actor, via, detail)
        row_hash = _row_hash(prev_hash, content)
        bind.execute(
            _CHANGE_LOG.update()
            .where(_CHANGE_LOG.c.id == row_id)
            .values(prev_hash=prev_hash, row_hash=row_hash)
        )
        prev_hash = row_hash

    with op.batch_alter_table("change_log", schema=None) as batch_op:
        batch_op.alter_column("prev_hash", nullable=False)
        batch_op.alter_column("row_hash", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("change_log", schema=None) as batch_op:
        batch_op.drop_column("row_hash")
        batch_op.drop_column("prev_hash")
