"""Per-user API tokens: minted here, stored only as a digest, revocable.

Deliberately *not* the scrypt of ``driftless/auth/passwords.py``. A password is
low-entropy and human-chosen, so it needs a slow KDF; a token minted here is 256 bits
of ``secrets`` randomness that no attacker guesses at any price, so its digest exists
only to make the stored value useless if the table leaks. Per-request scrypt would put
~16 MiB and tens of milliseconds on every API call and buy nothing — SHA-256 looked up
by equality is correct *and* fast. The plaintext exists once, as the mint's return
value: a lost token is re-minted, never recovered. :func:`resolve` reads the *user* row
back too, so deactivating a user kills every token they hold, as ``session_epoch`` does
for cookies.
"""

import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.auth.principal import Principal
from driftless.models import ApiToken, User

PREFIX = "dfl_"  # so a token leaked into a log or a repo is greppable


def mint() -> str:
    """A fresh 256-bit token; the only copy of the plaintext is this return value."""
    return f"{PREFIX}{secrets.token_urlsafe(32)}"  # 256 bits: guessing is off the table


def digest(token: str) -> str:  # the stored value: one-way, and fast on purpose
    return hashlib.sha256(token.encode()).hexdigest()


def issue(db: Session, user: User, label: str) -> str:
    """Mint a token for ``user``, store its digest, return the plaintext once."""
    token = mint()
    db.add(ApiToken(user_id=user.id, label=label, token_digest=digest(token)))
    db.commit()  # through the session, so the ChangeLog listener audits the mint
    return token


def revoke(db: Session, token_id: int) -> bool:
    """Stamp ``token_id`` revoked. ``False`` if there is no such live token."""
    row = db.scalars(select(ApiToken).where(ApiToken.id == token_id)).one_or_none()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = datetime.now(UTC)
    db.commit()
    return True


def resolve(db: Session, token: str) -> Principal | None:
    """The live identity behind a presented token; ``None`` — never a raise — for nobody."""
    if not token.startswith(PREFIX):
        return None
    row = db.scalars(select(ApiToken).where(ApiToken.token_digest == digest(token))).one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    user = db.get(User, row.user_id)  # read back: the token claims nothing about its owner
    if user is None or not user.is_active:
        return None
    return Principal(uid=user.id, username=user.username, role=user.role)
