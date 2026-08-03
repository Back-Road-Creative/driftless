"""Stored identity: who can sign in, and as what.

A user is a credential, a ``Person`` a resource; relating them would force every
staffed person to carry a login. ``app_user``, not ``user`` (reserved in
Postgres, the dialect this schema is proven against). Only the digest is stored;
``role`` sits behind the usual named CHECK, defaulting to the least-privileged
member. The login page and the request gate are the next PRs of this chain.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.hierarchy import one_of

USER_ROLES = ("admin", "contributor", "viewer")


def _utcnow() -> datetime:  # a write-time stamp, like ``SignOff.signed_at``
    return datetime.now(UTC)


class User(Base):
    """One login. Holds a password digest, never a password."""

    __tablename__ = "app_user"
    __table_args__ = (one_of("role", USER_ROLES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    is_active: Mapped[bool] = mapped_column(default=True)
    # Stamped into each session cookie: bumping it invalidates every cookie already
    # issued for this user, which is the only way a stateless session is revocable.
    session_epoch: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tokens: Mapped[list["ApiToken"]] = relationship(back_populates="user")


class ApiToken(Base):
    """One minted API token: a digest, never the token; unique, so a collision is refused."""

    __tablename__ = "api_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)
    label: Mapped[str] = mapped_column(String(100))  # what holds it, for the revoke decision
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)  # pragma: allowlist secret
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    user: Mapped[User] = relationship(back_populates="tokens")
