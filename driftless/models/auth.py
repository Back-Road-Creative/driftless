"""Stored identity: who can sign in, and as what.

A user is a credential, a ``Person`` a resource; relating them would force every
staffed person to carry a login. ``app_user``, not ``user`` (reserved in
Postgres, the dialect this schema is proven against). Only the digest is stored;
``role`` sits behind the usual named CHECK, defaulting to the least-privileged
member. The login page and the request gate are the next PRs of this chain.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import one_of

if TYPE_CHECKING:
    from driftless.models.notify import EmailSubscription
    from driftless.models.people import Person

USER_ROLES = ("admin", "contributor", "viewer")


def _utcnow() -> datetime:  # a write-time stamp, like ``SignOff.signed_at``
    return datetime.now(UTC)


class User(Base):
    """One login. Holds a password digest, never a password."""

    __tablename__ = "app_user"
    __table_args__ = (
        one_of("role", USER_ROLES),
        UniqueConstraint("oidc_subject", name="uq_app_user_oidc_subject"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    # Optional and unvalidated at the storage layer — the CLI is the one write path and
    # validates shape before this column is ever touched (``driftless.auth.cli``). No
    # uniqueness constraint: nothing here depends on it being distinct per login.
    email: Mapped[str | None] = mapped_column(String(255), default=None)
    # The IdP's ``sub`` this login is bound to, for OIDC sign-in
    # (``driftless.auth.oidc``) — unset means this user cannot sign in that way.
    # Unique so two logins can never share one external identity; nullable because
    # most rows predate the binding and password sign-in stays valid regardless.
    # Bound only by an admin (``driftless user oidc-subject``), never auto-written.
    oidc_subject: Mapped[str | None] = mapped_column(String(255), default=None)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    is_active: Mapped[bool] = mapped_column(default=True)
    # Stamped into each session cookie: bumping it invalidates every cookie already
    # issued for this user, which is the only way a stateless session is revocable.
    session_epoch: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tokens: Mapped[list["ApiToken"]] = relationship(back_populates="user")
    email_subscriptions: Mapped[list["EmailSubscription"]] = relationship(back_populates="user")


class ApiToken(Base):
    """One minted API token: a digest, never the token; unique, so a collision is refused."""

    __tablename__ = "api_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)
    label: Mapped[str] = mapped_column(String(100))  # what holds it, for the revoke decision
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)  # pragma: allowlist secret
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # ``None`` never expires — the default, so a token minted before this column existed
    # keeps working unchanged. Checked once, at ``tokens.resolve``: see that module.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # ``None`` means "never seen used", which is the only thing that is honestly known
    # about a token minted before this column existed as well as one nobody has spent.
    # Written by ``tokens.resolve`` and COARSE on purpose — see ``tokens.STAMP_INTERVAL``.
    # Telemetry about the credential, not a domain write: it is deliberately kept out of
    # the audit trail, which is why ``resolve`` writes it with Core SQL.
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    user: Mapped[User] = relationship(back_populates="tokens")
    # The agent Person(s) this token authenticates on behalf of — ONETOMANY so the
    # delete guard can name "still has people" instead of an opaque constraint 409;
    # in practice a token binds at most one agent. See ``Person.agent_token``.
    agent_people: Mapped[list["Person"]] = relationship(back_populates="agent_token")
