"""Preview, apply and confirm one native change, over the write paths that
already exist in this package rather than a second one.

``preview`` reads what a change WOULD write with no write of its own;
``apply`` performs it through the validated service the API and the web
already call (never ``session.add`` directly, so a change taken through this
module cannot skip the checks either surface already enforces); ``confirm``
records that an applied change was reviewed. Every function is a thin
dispatch over the two change kinds :mod:`driftless.services` can write today
— a status snapshot and the sign-off the onboarding wizard and the threat
board both file — because those are the only two native writes this package
exposes as a session-level service rather than only a route. Adding a third
kind means adding a branch here and a matching entry in
``driftless.pmbok.consumers`` — not a second module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.services.sign_offs import create_sign_off
from driftless.services.status_snapshots import create_status_snapshot


def _utcnow() -> datetime:
    """Now, in UTC — the one wall-clock read in this module, stamped on a
    confirmation at the moment it is made. Never read by a preview or an apply,
    both of which take their own as-of from the change they are given."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class StatusSnapshotChange:
    """Write one weekly status snapshot — :func:`create_status_snapshot`'s payload."""

    payload: s.StatusSnapshotIn
    kind: str = field(default="status_snapshot", init=False)


@dataclass(frozen=True, slots=True)
class SignOffChange:
    """Append one sign-off ledger entry — :func:`create_sign_off`'s payload.

    ``signed_by`` on the payload is never trusted; ``apply`` stamps the actor
    it is called with, exactly as the API and the web already do.
    """

    payload: s.SignOffIn
    kind: str = field(default="sign_off", init=False)


Change = StatusSnapshotChange | SignOffChange

#: Every table a change kind can write to, in the order ``apply`` writes it —
#: the vocabulary :mod:`driftless.pmbok.consumers` keys its declarations by.
CHANGE_KINDS: tuple[str, ...] = ("status_snapshot", "sign_off")


@dataclass(frozen=True, slots=True)
class Preview:
    """Every row a change WOULD write, described by table name — no write made.

    One entry per row ``apply`` will insert. A row's real id does not exist
    yet, so this names the table it lands in rather than an id it cannot
    predict; ``Applied.row_ids`` is where the real ids show up once the write
    has actually happened.
    """

    kind: str
    would_touch: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Applied:
    """The rows a change actually wrote: ids and revisions, keyed by table.

    ``revisions`` carries ``None`` for a table with no ``row_revision``
    column (both of today's two do not) rather than inventing one — a
    revision this module never wrote must never be reported as one.
    """

    kind: str
    row_ids: dict[str, tuple[int, ...]]
    revisions: dict[str, tuple[int | None, ...]]


@dataclass(frozen=True, slots=True)
class Confirmed:
    """A signed acknowledgement that an applied change was reviewed.

    Modelled on the sign-off ledger's own shape — immutable and actor-stamped
    — without adding a table: a second look at the same ``Applied`` is a new
    ``Confirmed``, never a mutation of the first, so there is nothing here to
    edit or delete.
    """

    applied: Applied
    actor: str
    confirmed_at: datetime


def preview(session: Session, change: Change) -> Preview:
    """What ``apply`` would write for ``change`` — a read, never a write.

    Both change kinds insert exactly one row today, so this only needs to
    name which table it lands in; a caller that wants the values the row
    would carry already holds ``change.payload``.
    """
    if isinstance(change, StatusSnapshotChange):
        return Preview(change.kind, ("status_snapshot",))
    if isinstance(change, SignOffChange):
        return Preview(change.kind, ("sign_off",))
    raise TypeError(f"unknown change: {change!r}")  # pragma: no cover — Change is exhaustive


def apply(session: Session, change: Change, *, actor: str) -> Applied:
    """Write ``change`` through the service its kind already has, never a
    second write path — ``session.add`` never appears in this module."""
    if isinstance(change, StatusSnapshotChange):
        row = create_status_snapshot(session, change.payload, actor)
        return Applied(
            change.kind,
            {"status_snapshot": (row.id,)},
            {"status_snapshot": (getattr(row, "row_revision", None),)},
        )
    if isinstance(change, SignOffChange):
        sign_off = create_sign_off(session, change.payload, signed_by=actor)
        return Applied(
            change.kind,
            {"sign_off": (sign_off.id,)},
            {"sign_off": (getattr(sign_off, "row_revision", None),)},
        )
    raise TypeError(f"unknown change: {change!r}")  # pragma: no cover — Change is exhaustive


def confirm(session: Session, applied: Applied, *, actor: str) -> Confirmed:
    """Acknowledge ``applied`` was reviewed. Always a NEW record — there is no
    update, matching the append-only ledgers this mirrors."""
    return Confirmed(applied=applied, actor=actor, confirmed_at=_utcnow())
