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
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from driftless.auth.principal import Principal
from driftless.models import ApiToken, Person, User

PREFIX = "dfl_"  # so a token leaked into a log or a repo is greppable

#: How stale a stored ``last_used_at`` may get before the next use rewrites it.
#:
#: The question the column answers — "is anything still holding this token, or can I
#: revoke it?" — is asked by a human reading ``token list``, and a quarter hour is far
#: finer than that decision needs. Stamping every request instead would put a write on
#: the authenticated READ path: every GET, every list, every page render, for a value
#: nobody reads to the minute. Coarse and cheap beats exact and expensive here.
STAMP_INTERVAL = timedelta(minutes=15)


def stamped(moment: datetime) -> datetime:
    """SQLite hands the offset back stripped, so a naive value is read as the UTC it
    was written as, never as local time (same fix as ``assess.adapters._utc_date``).

    Public: ``auth.cli`` needs the same normalization to render a token's state, and a
    helper two modules depend on carries a public name rather than a borrowed private one.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def mint() -> str:
    """A fresh 256-bit token; the only copy of the plaintext is this return value."""
    return f"{PREFIX}{secrets.token_urlsafe(32)}"  # 256 bits: guessing is off the table


def digest(token: str) -> str:  # the stored value: one-way, and fast on purpose
    return hashlib.sha256(token.encode()).hexdigest()


def issue(db: Session, user: User, label: str, *, expires_at: datetime | None = None) -> str:
    """Mint a token for ``user``, store its digest, return the plaintext once.

    ``expires_at`` is ``None`` by default: a token minted with no expiry never
    expires, which is also what every token minted before this column existed
    keeps meaning.
    """
    token = mint()
    db.add(
        ApiToken(user_id=user.id, label=label, token_digest=digest(token), expires_at=expires_at)
    )
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


def _stamp_use(db: Session, row: ApiToken, now: datetime) -> None:
    """Record that ``row`` was just presented, if the stored value is stale enough to be
    worth a write (see :data:`STAMP_INTERVAL`; an unstamped token is always worth one).

    A Core ``UPDATE`` rather than an ORM assignment, and that is the point rather than a
    style choice. The session factory this runs under carries the ChangeLog listener
    (:func:`driftless.db.changelog.register_changelog`), which audits every *instance* a
    flush finds dirty — so assigning ``row.last_used_at`` would file an audit row every
    time a token authenticated, burying the trail of who changed what under a log of who
    read something. Statement-level SQL leaves no instance dirty and so writes no entry.
    Last use is telemetry about a credential; the trail is for domain writes by an actor.

    Committed here, because ``driftless.db.session_scope`` yields a session and closes it
    without committing: an uncommitted stamp is a silently dropped one, which would leave
    this column reading "never used" forever while looking implemented.
    """
    if row.last_used_at is not None and stamped(now) - stamped(row.last_used_at) < STAMP_INTERVAL:
        return
    db.execute(update(ApiToken).where(ApiToken.id == row.id).values(last_used_at=now))
    db.commit()


def resolve(db: Session, token: str, now: datetime) -> Principal | None:
    """The live identity behind a presented token; ``None`` — never a raise — for nobody.

    ``now`` is threaded in rather than read here, so this stays testable at a boundary
    with no monkeypatching (see ``api.secure.TokenGate``, which threads its own clock the
    same way). An expired token and a revoked token resolve identically — both ``None`` —
    on purpose: a caller learning WHICH of the two happened is a disclosure with no
    legitimate use. The operator-facing distinction lives in ``token list`` (``auth.cli``),
    never here.

    A resolution that admits somebody also stamps ``last_used_at``, so an operator can
    tell a token still in use from one whose holder is long gone — see :func:`_stamp_use`
    for why that write is coarse and why it is not an ORM assignment.
    """
    if not token.startswith(PREFIX):
        return None
    row = db.scalars(select(ApiToken).where(ApiToken.token_digest == digest(token))).one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    # BOTH sides normalized, not just the stored one: comparing an aware datetime to a
    # naive one raises TypeError, and this comparison sits on the authenticated path —
    # a caller threading a naive clock would turn every request carrying an expiring
    # token into a 500. The rule this module already states (a naive value is the UTC it
    # was written as) is the one applied, rather than leaving a crash to discover.
    if row.expires_at is not None and stamped(row.expires_at) <= stamped(now):
        return None
    user = db.get(User, row.user_id)  # read back: the token claims nothing about its owner
    if user is None or not user.is_active:
        return None
    is_agent = (
        db.scalars(
            select(Person.id).where(Person.agent_token_id == row.id, Person.kind == "agent")
        ).first()
        is not None
    )
    who = Principal(uid=user.id, username=user.username, role=user.role, is_agent=is_agent)
    _stamp_use(db, row, now)  # only a token that actually admitted somebody counts as used
    return who
