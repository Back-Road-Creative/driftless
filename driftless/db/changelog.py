"""The append-only ChangeLog: who changed what, when, and what the values were.

Logging runs off a SQLAlchemy flush listener, not off calls at each write site: a
per-endpoint convention is something a future writer forgets, and the gap stays invisible
until somebody asks "who changed this?" and the answer is missing. A session listener
cannot be bypassed by any code path that writes through a session.

Two hooks, one mechanism. ``before_flush`` captures the old values, which exist only
before the unit of work is resolved. ``after_flush`` writes the rows, the first moment a
freshly inserted row has a primary key — one logged without a key points at nothing.
Activation is explicit (``register_changelog``), never an import side effect, so
importing this module instruments nothing on its own. The log is append-only: nothing
here updates or deletes a ChangeLog row, and a ChangeLog write is never itself logged,
which would recurse. ``detail`` is JSON *text* rather than a JSON column, so the table
stays portable between SQLite and Postgres.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    and_,
    event,
    insert,
    inspect,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from driftless.db.base import Base

#: ``session.info`` key holding the actor credited with every write in that session.
ACTOR_KEY = "driftless_actor"
_PENDING_KEY = "driftless_changelog_pending"


def _utcnow() -> datetime:
    """Now, in UTC. SQLite drops the offset on the way back out; the value is UTC either way."""
    return datetime.now(UTC)


class ChangeLog(Base):
    """One immutable row per mutation. The flush listener is its only writer."""

    __tablename__ = "change_log"
    __table_args__ = (
        CheckConstraint("operation IN ('insert', 'update', 'delete')", name="ck_operation"),
        # The log is written once and read by identity: "everything that happened to THIS
        # row". ``assess.adapters.progress_history`` replays a task's percentage out of it
        # on the equality pair below, so with no index the planner reads the entire log to
        # answer one project — measured on SQLite as a full SCAN, or a throwaway AUTOMATIC
        # index rebuilt per execution — and that cost grows with the audit trail rather
        # than with the project. The pair leads because that is what the read filters on;
        # ``changed_at`` trails it as the range/order column a history read asks for next.
        Index("ix_change_log_table_row_changed", "table_name", "row_id", "changed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    table_name: Mapped[str] = mapped_column(String(100))
    row_id: Mapped[str] = mapped_column(String(100))
    operation: Mapped[str] = mapped_column(String(10))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    actor: Mapped[str | None] = mapped_column(String(200), default=None)
    detail: Mapped[str] = mapped_column(Text, default="{}")


@dataclass(frozen=True)
class _Pending:
    """A change seen at ``before_flush``. ``target`` is set for inserts only."""

    table_name: str
    operation: str
    actor: str | None
    target: object | None = None
    row_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def set_actor(session: Session, actor: str | None) -> None:
    """Credit every later write in ``session`` to ``actor``. ``None`` means a system write."""
    session.info[ACTOR_KEY] = actor


def register_changelog(target: sessionmaker[Session] | Session | type[Session]) -> None:
    """Activate change logging for ``target`` — a sessionmaker, a Session, or the Session class."""
    event.listen(target, "before_flush", _capture)
    event.listen(target, "after_flush", _write)


def _jsonable(value: Any) -> Any:
    """Coerce a column value to something ``json.dumps`` accepts, losing nothing readable."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return value.isoformat() if isinstance(value, date) else str(value)


def _mapper(obj: Any) -> Any:
    return inspect(obj).mapper


def _table_name(obj: Any) -> str:
    return str(_mapper(obj).local_table.name)


def _row_id(obj: Any) -> str:
    """PK as text, off the instance: at ``after_flush`` ``state.identity`` is still None."""
    return ",".join(str(part) for part in _mapper(obj).primary_key_from_instance(obj))


def _column_values(obj: Any) -> dict[str, Any]:
    state = inspect(obj)
    return {attr.key: _jsonable(state.dict.get(attr.key)) for attr in state.mapper.column_attrs}


def _stored_values(session: Session, obj: Any, keys: list[str]) -> dict[str, Any]:
    """What the database currently holds for ``keys`` — the truthful "old" side.

    Read from the row, not from attribute history: a commit expires the instance, and
    assigning to an expired attribute discards the previous value, so history alone would
    report every old value as ``None`` and the trail would be a fiction.
    """
    if not keys:
        return {}
    mapper = _mapper(obj)
    pk = zip(mapper.primary_key, mapper.primary_key_from_instance(obj), strict=True)
    where = and_(*(column == value for column, value in pk))
    columns = [mapper.columns[key] for key in keys]
    row = session.connection().execute(select(*columns).where(where)).one_or_none()
    return {} if row is None else {k: _jsonable(v) for k, v in zip(keys, row, strict=True)}


def _changed_columns(session: Session, obj: Any) -> dict[str, dict[str, Any]]:
    """Old/new per column that actually moved. Rewriting a value with itself is not a change."""
    state = inspect(obj)
    keys = [a.key for a in state.mapper.column_attrs if state.attrs[a.key].history.has_changes()]
    stored = _stored_values(session, obj, keys)
    pairs = {k: {"old": stored.get(k), "new": _jsonable(state.dict.get(k))} for k in keys}
    return {k: v for k, v in pairs.items() if v["old"] != v["new"]}


def _capture(session: Session, flush_context: Any, instances: Any) -> None:
    """Record what this flush is about to do, while the old values still exist."""
    actor = session.info.get(ACTOR_KEY)
    pending: list[_Pending] = []
    for obj in session.new:
        if not isinstance(obj, ChangeLog):
            pending.append(_Pending(_table_name(obj), "insert", actor, target=obj))
    for obj in session.dirty:
        changed = {} if isinstance(obj, ChangeLog) else _changed_columns(session, obj)
        if changed:
            detail = {"changed": changed}
            pending.append(_Pending(_table_name(obj), "update", actor, None, _row_id(obj), detail))
    for obj in session.deleted:
        if isinstance(obj, ChangeLog):
            continue
        old = {"old": _stored_values(session, obj, [a.key for a in _mapper(obj).column_attrs])}
        pending.append(_Pending(_table_name(obj), "delete", actor, None, _row_id(obj), old))
    session.info[_PENDING_KEY] = pending


def _write(session: Session, flush_context: Any) -> None:
    """Write the captured changes now that inserted rows carry their primary keys."""
    pending: list[_Pending] = session.info.pop(_PENDING_KEY, [])
    if not pending:
        return
    stamped_at = _utcnow()
    rows = [
        {
            "table_name": entry.table_name,
            "row_id": entry.row_id if entry.target is None else _row_id(entry.target),
            "operation": entry.operation,
            "changed_at": stamped_at,
            "actor": entry.actor,
            "detail": json.dumps(
                entry.detail if entry.target is None else {"new": _column_values(entry.target)},
                sort_keys=True,
            ),
        }
        for entry in pending
    ]
    session.connection().execute(insert(ChangeLog), rows)
