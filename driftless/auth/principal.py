"""Who the request is — read back from the store, never taken from the cookie.

A signed cookie proves only that this service issued it, so the payload is an
identity *claim* and never the authority: :func:`resolve` reads the row and
refuses a login that has since been deactivated or whose ``session_epoch`` has
moved past the one stamped into the cookie. That epoch is what makes a stateless
session revocable at all — bumping the counter kills every cookie already out
there, with no server-side session table to sweep.

Absence fails closed. A payload carrying no ``epc`` is refused rather than
grandfathered in, because such a cookie predates revocation and nothing could
ever revoke it; the cost of that strictness is one forced sign-in, and the cost
of the alternative is a permanent bypass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.auth.sessions import plain_int
from driftless.models import User


@dataclass(frozen=True)
class Principal:
    """The identity the store still vouches for — not the one the cookie claimed."""

    uid: int
    username: str
    role: str
    #: Whether this identity is an agent Person's bound credential rather than a
    #: human's — set only by ``driftless.auth.tokens.resolve`` (a cookie login is
    #: always human); read by the sign-off write path to refuse an agent decision
    #: unless ``DRIFTLESS_ALLOW_AGENT_SIGNOFF=1``.
    is_agent: bool = False


def resolve(db: Session, payload: dict[str, Any]) -> Principal | None:
    """The live identity behind a verified cookie payload, or ``None`` for no identity."""
    uid, epoch = payload.get("uid"), payload.get("epc")
    if not plain_int(uid) or not plain_int(epoch):  # unstamped cookies are not trusted
        return None
    user = db.scalars(select(User).where(User.id == uid)).one_or_none()
    if user is None or not user.is_active or user.session_epoch != epoch:
        return None
    return Principal(uid=user.id, username=user.username, role=user.role)
