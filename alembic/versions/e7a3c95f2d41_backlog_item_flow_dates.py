"""backlog_item: store the three flow dates instead of guessing them

``created_on``/``started_on``/``done_on`` in EFFECTIVE time. ``pmbok.flow_facts`` used to
derive those three by replaying the append-only ``ChangeLog``, which dates an item by the
wall clock at the moment its row was WRITTEN — so a store seeded, imported or restored into
a fresh database today and read at an earlier as-of anchor had no replayable history at all:
every item fell back to ``date.min``, every completion sat outside the trailing-week
throughput window and both duration medians were structurally zero.

All three are nullable and nothing must fill them: a row this backfill cannot date honestly
keeps a null ``created_on``, the very marker the read path uses to fall back to the replay,
so no deployment loses history. The replay runs in Python because ``detail`` is JSON *text*,
portable between the dialects; an item logged ``done`` before it was ever logged
``in_progress`` — reopened — has no cycle to time, so its start is dropped rather than written
inverted, which is what the added CHECK refuses. ``batch_alter_table`` is dialect-conditional
(``alembic/env.py``): SQLite rebuilds the table copy-and-swap once, before the backfill.

Revision ID: e7a3c95f2d41
Revises: d4f8b3e19a72
Create Date: 2026-08-30 09:00:00.000000

"""

import json
from collections.abc import Sequence
from datetime import UTC, date
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "e7a3c95f2d41"  # pragma: allowlist secret  (alembic revision id, not a credential)
down_revision: str | None = "d4f8b3e19a72"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Worded exactly as the model words it, and pinned literally: history is frozen.
_CHECK = "ck_backlog_item_flow_dates"
_IN_ORDER = (
    "(started_on IS NULL OR created_on IS NULL OR started_on >= created_on)"
    " AND (done_on IS NULL OR created_on IS NULL OR done_on >= created_on)"
    " AND (done_on IS NULL OR started_on IS NULL OR done_on >= started_on)"
)
_COLUMNS = ("created_on", "started_on", "done_on")

_LOGGED = sa.text(
    "SELECT row_id, operation, changed_at, detail FROM change_log"
    " WHERE table_name = 'backlog_item' ORDER BY changed_at, id"
).columns(changed_at=sa.DateTime(timezone=True))
_BACKLOG_ITEM = sa.table(
    "backlog_item",
    sa.column("id", sa.Integer),
    *(sa.column(name, sa.Date) for name in _COLUMNS),
)


def _replayed(rows: Sequence[Any]) -> dict[int, tuple[date, date | None, date | None]]:
    """The three dates per backlog-item id, replayed off log rows ordered oldest first."""
    inserted: dict[str, date] = {}
    observed: dict[str, list[tuple[date, str]]] = {}
    for row_id, operation, changed_at, detail in rows:
        stamped = changed_at if changed_at.tzinfo else changed_at.replace(tzinfo=UTC)
        on = stamped.astimezone(UTC).date()
        if operation == "delete":  # a reborn id must not inherit a dead row's dates
            inserted.pop(row_id, None)
            observed.pop(row_id, None)
            continue
        if operation == "insert":
            inserted[row_id] = on
        body = json.loads(detail)  # the ``status`` this row moved, if it moved one at all
        status = (
            body.get("new", {}).get("status")
            if operation == "insert"
            else body.get("changed", {}).get("status", {}).get("new")
        )
        if isinstance(status, str):
            observed.setdefault(row_id, []).append((on, status))
    dates: dict[int, tuple[date, date | None, date | None]] = {}
    for row_id, statuses in observed.items():
        created = inserted.get(row_id)
        if created is None:  # no logged insert — nothing honest to write, so leave it null
            continue
        started = next((on for on, s in statuses if s == "in_progress"), None)
        done = next((on for on, s in statuses if s == "done"), None)
        if started is not None and done is not None and done < started:
            started = None  # done before it was ever started: no cycle to time
        dates[int(row_id)] = (created, started, done)
    return dates


def upgrade() -> None:
    with op.batch_alter_table("backlog_item", schema=None) as batch_op:
        for name in _COLUMNS:
            batch_op.add_column(sa.Column(name, sa.Date(), nullable=True))
        batch_op.create_check_constraint(_CHECK, _IN_ORDER)

    bind = op.get_bind()
    for row_id, dates in _replayed(bind.execute(_LOGGED).all()).items():
        bind.execute(
            _BACKLOG_ITEM.update()
            .where(_BACKLOG_ITEM.c.id == row_id)
            .values(dict(zip(_COLUMNS, dates, strict=True)))
        )


def downgrade() -> None:
    with op.batch_alter_table("backlog_item", schema=None) as batch_op:
        batch_op.drop_constraint(_CHECK, type_="check")
        for name in reversed(_COLUMNS):
            batch_op.drop_column(name)
