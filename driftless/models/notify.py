"""``WebhookSubscription``: a URL subscribed to ``ChangeLog`` rows, cursored.

Only ``last_delivered_changelog_id`` is stored state. ``secret`` is the raw HMAC
signing key, not a digest — a digest cannot sign anything.

``EmailSubscription`` is the same cursor shape applied to the attention feed
instead of ``ChangeLog``: one row per user wanting a periodic digest, cursored
by ``last_sent_as_of`` rather than a row id, because the digest's unit of work
is a rendered as-of date, not a delivered row.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from driftless.db import Base
from driftless.models.auth import User
from driftless.models.hierarchy import one_of

EMAIL_DIGEST_CADENCES = ("daily", "weekly", "monthly")

_HTTPS_OR_LOCAL_HTTP = (
    "url LIKE 'https://%' OR url LIKE 'http://127.0.0.1%' OR url LIKE 'http://localhost%'"
)


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscription"
    __table_args__ = (CheckConstraint(_HTTPS_OR_LOCAL_HTTP, name="ck_webhook_subscription_https"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(2000))
    secret: Mapped[str] = mapped_column(String(500))  # pragma: allowlist secret
    events: Mapped[str] = mapped_column(Text, default="*")
    last_delivered_changelog_id: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)


class EmailSubscription(Base):
    """One user's standing request for a periodic attention-list digest."""

    __tablename__ = "email_subscription"
    __table_args__ = (one_of("cadence", EMAIL_DIGEST_CADENCES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)
    cadence: Mapped[str] = mapped_column(String(20), default="weekly")
    # The as-of date the last successful send rendered. ``None`` means never sent.
    # Advanced only after ``smtplib`` reports the message accepted — a failed send
    # leaves the cursor put, so the next run resends the same as-of rather than
    # silently skipping it.
    last_sent_as_of: Mapped[date | None] = mapped_column(default=None)

    user: Mapped[User] = relationship(back_populates="email_subscriptions")
