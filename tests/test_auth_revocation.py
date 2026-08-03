"""Contract for revocable sessions: the per-user epoch and the principal resolver.

A signed cookie proves only that this service issued it, never that the login is
still good. Pinned here: a payload resolves to a principal while its user is
active and its ``epc`` still matches the row, and stops the moment either moves.
A payload with no ``epc`` at all never resolves — fail closed, because a cookie
minted before epochs existed is a cookie nothing can revoke.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from driftless.auth import principal, sessions
from driftless.models import User

NOW = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)
SECRET = "test-signing-secret"  # pragma: allowlist secret  (throwaway in-test signing key)


def _user(db: Session) -> User:
    user = User(username="jp", password_hash="x", role="admin")
    db.add(user)
    db.commit()
    return user


def _payload(user: User) -> dict[str, Any]:
    """What a login hands the gate: a verified payload stamped with the live epoch."""
    value = sessions.issue(user.id, user.username, user.role, LATER, SECRET, user.session_epoch)
    verified = sessions.verify(value, SECRET, NOW)
    assert verified is not None
    return verified


def test_a_live_user_resolves_to_the_role_the_store_holds(db: Session) -> None:
    user = _user(db)
    who = principal.resolve(db, _payload(user))
    assert who is not None
    assert (who.uid, who.username, who.role) == (user.id, "jp", "admin")


def test_the_same_cookie_stops_resolving_once_the_epoch_is_bumped(db: Session) -> None:
    user = _user(db)
    captured = _payload(user)
    assert principal.resolve(db, captured) is not None
    user.session_epoch += 1  # exactly what ``driftless user disable`` does
    db.commit()
    assert principal.resolve(db, captured) is None


def test_the_same_cookie_stops_resolving_once_the_user_is_deactivated(db: Session) -> None:
    user = _user(db)
    captured = _payload(user)
    user.is_active = False
    db.commit()
    assert principal.resolve(db, captured) is None


def test_a_payload_carrying_no_epoch_never_resolves(db: Session) -> None:
    user = _user(db)
    value = sessions.issue(user.id, user.username, user.role, LATER, SECRET)  # no epoch passed
    unstamped = sessions.verify(value, SECRET, NOW)
    assert unstamped is not None and "epc" not in unstamped  # verifies, but is not authority
    assert principal.resolve(db, unstamped) is None


def test_an_unknown_user_and_a_flag_shaped_id_are_both_refused(db: Session) -> None:
    user = _user(db)
    assert principal.resolve(db, {"uid": user.id + 99, "epc": 0}) is None
    # ``True`` is an ``int``, and ``id == True`` would otherwise match the first row.
    assert principal.resolve(db, {"uid": True, "epc": 0}) is None
