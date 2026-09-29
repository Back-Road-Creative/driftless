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

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, NamedTuple

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
from driftless.models.hierarchy import one_of

#: ``session.info`` key holding the actor credited with every write in that session.
ACTOR_KEY = "driftless_actor"
#: ``session.info`` key holding the channel credited with every write in that session.
VIA_KEY = "driftless_via"
_PENDING_KEY = "driftless_changelog_pending"

#: The closed vocabulary ``via`` is drawn from. ``mcp`` is reserved for the MCP server,
#: a separate unit that writes through the same session-level API and stamps its own
#: channel the same way every other entry point here does.
CHANGE_CHANNELS = ("web", "api", "cli", "mcp")

#: ``prev_hash`` of the very first row in the log. Sixty-four ``0`` characters — the same
#: length a sha256 hex digest carries — rather than an empty string or ``NULL``, so the
#: genesis link is a value ``verify_chain`` compares like any other hash, not a special
#: case it has to know about. Frozen the moment the chain is proved: changing it would
#: break every already-migrated store's first row.
GENESIS_HASH = "0" * 64

#: The columns a row's hash is taken over, in canonical (sorted) form. ``id``,
#: ``prev_hash`` and ``row_hash`` are excluded on purpose: ``id`` is storage, not content,
#: and the other two are what this hash *produces*, not what it is taken over.
_CONTENT_FIELDS = ("table_name", "row_id", "operation", "changed_at", "actor", "via", "detail")


def _utcnow() -> datetime:
    """Now, in UTC. SQLite drops the offset on the way back out; the value is UTC either way."""
    return datetime.now(UTC)


class ChangeLog(Base):
    """One immutable row per mutation. The flush listener is its only writer."""

    __tablename__ = "change_log"
    __table_args__ = (
        CheckConstraint("operation IN ('insert', 'update', 'delete')", name="ck_operation"),
        # NULL passes a CHECK (the row predates this column, or nothing ever stamped a
        # channel on the write), so the same ``one_of`` idiom the rest of the schema uses
        # for a closed vocabulary works here unmodified — old rows keep ``via=None``.
        one_of("via", CHANGE_CHANNELS),
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
    #: The channel the write came through — one of ``CHANGE_CHANNELS``, or ``None`` for
    #: a row written before this column existed or through a caller that never set it.
    via: Mapped[str | None] = mapped_column(String(20), default=None)
    detail: Mapped[str] = mapped_column(Text, default="{}")
    #: The previous row's ``row_hash``, or ``GENESIS_HASH`` for the first row. Chains the
    #: log so deleting or rewriting any row — even the *last* one, which an edit-in-place
    #: attack would otherwise leave undetected — breaks the link the next row (if any) or
    #: a re-walk of the whole table can see.
    prev_hash: Mapped[str] = mapped_column(String(64), default=GENESIS_HASH)
    #: sha256 of ``prev_hash`` concatenated with this row's own canonical content. See
    #: ``verify_chain``.
    row_hash: Mapped[str] = mapped_column(String(64), default=GENESIS_HASH)


@dataclass(frozen=True)
class _Pending:
    """A change seen at ``before_flush``. ``target`` is set for inserts only."""

    table_name: str
    operation: str
    actor: str | None
    via: str | None
    target: object | None = None
    row_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def set_actor(session: Session, actor: str | None) -> None:
    """Credit every later write in ``session`` to ``actor``. ``None`` means a system write."""
    session.info[ACTOR_KEY] = actor


def set_via(session: Session, via: str | None) -> None:
    """Credit every later write in ``session`` to the ``via`` channel it came through.

    Set once, at the session's own entry point — ``driftless.api.deps.get_session`` for
    every API and web request, and each CLI command's own session opener — the same way
    ``ACTOR_KEY`` is set once and then re-stamped, idempotently, by any service function
    nested under it. ``None`` means unknown, never a fourth vocabulary member.
    """
    if via is not None and via not in CHANGE_CHANNELS:
        raise ValueError(f"via must be one of {CHANGE_CHANNELS}, got {via!r}")
    session.info[VIA_KEY] = via


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
    via = session.info.get(VIA_KEY)
    pending: list[_Pending] = []
    for obj in session.new:
        if not isinstance(obj, ChangeLog):
            pending.append(_Pending(_table_name(obj), "insert", actor, via, target=obj))
    for obj in session.dirty:
        changed = {} if isinstance(obj, ChangeLog) else _changed_columns(session, obj)
        if changed:
            detail = {"changed": changed}
            pending.append(
                _Pending(_table_name(obj), "update", actor, via, None, _row_id(obj), detail)
            )
    for obj in session.deleted:
        if isinstance(obj, ChangeLog):
            continue
        old = {"old": _stored_values(session, obj, [a.key for a in _mapper(obj).column_attrs])}
        pending.append(_Pending(_table_name(obj), "delete", actor, via, None, _row_id(obj), old))
    session.info[_PENDING_KEY] = pending


def _canonical_timestamp(changed_at: datetime) -> str:
    """A hashable, engine-independent form of ``changed_at``.

    SQLite drops the UTC offset on the way back out of the database (see the module
    docstring); Postgres keeps it. Normalising every aware value to naive UTC before
    hashing means a row written on one engine and re-read on the other — or simply
    re-read after a round trip through SQLite — still reproduces the hash it was given
    at write time, rather than reporting spurious tampering on every honest read.
    """
    if changed_at.tzinfo is not None:
        changed_at = changed_at.astimezone(UTC).replace(tzinfo=None)
    return changed_at.isoformat()


def _content(
    *,
    table_name: str,
    row_id: str,
    operation: str,
    changed_at: datetime,
    actor: str | None,
    via: str | None,
    detail: str,
) -> dict[str, Any]:
    """The fields a row's hash is taken over, keyed for canonical (sorted) JSON."""
    values = (table_name, row_id, operation, _canonical_timestamp(changed_at), actor, via, detail)
    return dict(zip(_CONTENT_FIELDS, values, strict=True))


def _row_hash(prev_hash: str, content: dict[str, Any]) -> str:
    """sha256 of ``prev_hash`` plus the row's own canonical content — the chain link."""
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


def _last_hash(session: Session) -> str:
    """The most recently written row's ``row_hash``, or ``GENESIS_HASH`` if the log is empty."""
    stored = (
        session.connection()
        .execute(select(ChangeLog.row_hash).order_by(ChangeLog.id.desc()).limit(1))
        .scalar()
    )
    return GENESIS_HASH if stored is None else str(stored)


class ChainBreak(NamedTuple):
    """Where ``verify_chain`` found the log's history no longer matches its hashes."""

    row_id: int
    reason: str


def verify_chain(session: Session) -> ChainBreak | None:
    """Walk the log in id order, recomputing each row's hash. ``None`` means the whole
    chain is intact; otherwise the first row where it is not, and why.

    A tampered ``prev_hash`` or content, and a deleted row, are both caught here: a
    deletion leaves the surviving next row's ``prev_hash`` pointing at a hash the actual
    previous row (in the id order this walk sees) never produced.
    """
    prev_hash = GENESIS_HASH
    for row in session.scalars(select(ChangeLog).order_by(ChangeLog.id)):
        if row.prev_hash != prev_hash:
            return ChainBreak(row.id, "prev_hash does not match the previous row's row_hash")
        content = _content(
            table_name=row.table_name,
            row_id=row.row_id,
            operation=row.operation,
            changed_at=row.changed_at,
            actor=row.actor,
            via=row.via,
            detail=row.detail,
        )
        if row.row_hash != _row_hash(prev_hash, content):
            return ChainBreak(row.id, "row_hash does not match this row's content")
        prev_hash = row.row_hash
    return None


def _write(session: Session, flush_context: Any) -> None:
    """Write the captured changes now that inserted rows carry their primary keys."""
    pending: list[_Pending] = session.info.pop(_PENDING_KEY, [])
    if not pending:
        return
    stamped_at = _utcnow()
    prev_hash = _last_hash(session)
    rows = []
    for entry in pending:
        row_id = entry.row_id if entry.target is None else _row_id(entry.target)
        assert row_id is not None  # set on every _Pending whose target is None
        detail = json.dumps(
            entry.detail if entry.target is None else {"new": _column_values(entry.target)},
            sort_keys=True,
        )
        content = _content(
            table_name=entry.table_name,
            row_id=row_id,
            operation=entry.operation,
            changed_at=stamped_at,
            actor=entry.actor,
            via=entry.via,
            detail=detail,
        )
        row_hash = _row_hash(prev_hash, content)
        rows.append(
            {
                "table_name": entry.table_name,
                "row_id": row_id,
                "operation": entry.operation,
                "changed_at": stamped_at,
                "actor": entry.actor,
                "via": entry.via,
                "detail": detail,
                "prev_hash": prev_hash,
                "row_hash": row_hash,
            }
        )
        prev_hash = row_hash
    session.connection().execute(insert(ChangeLog), rows)
