"""The one stale-write rule, shared by every surface that patches or deletes a row.

Lived in :mod:`driftless.api.crud` alone until the wizard and web surfaces needed a
write boundary of their own to reuse — a second copy of "refuse a stale ``If-Match``"
is exactly the drift a shared rule exists to rule out. ``driftless.api.crud`` imports
:func:`check_revision` from here rather than keeping its own; nothing else changed
about *when* it runs or what it raises.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def check_revision(row: Any, stated_revision: int | None) -> None:
    """Refuse a write whose stated revision no longer names the row's current state.

    ``row`` is typed ``Any`` rather than a bound TypeVar: ``row_revision`` is the
    concurrency token every PATCH/DELETE-able model carries
    (``driftless.models.hierarchy`` module docstring), but the shared ``Base`` does
    not declare it, so a statically-typed row cannot read it back.

    ``stated_revision`` of ``None`` means "no precondition stated" and is never a
    stale write — the caller that means to race checks, and one that does not
    keeps writing unconditionally exactly as it always could. Checked first, ahead
    of every other write rule: a stale precondition means the caller was editing a
    row that has already moved, and no other validation is worth running against a
    row it no longer describes. The 409 carries the row's current revision, so a
    client that lost the race can re-read and retry instead of silently
    overwriting the row it raced.
    """
    if stated_revision is not None and stated_revision != row.row_revision:
        raise HTTPException(
            409,
            f"{type(row).__name__} {row.id} is at revision {row.row_revision}, not "
            f"{stated_revision} -- re-read and retry",
        )
