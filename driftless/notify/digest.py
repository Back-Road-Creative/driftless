"""``driftless notify digest``: email the attention feed to subscribed users.

Renders the SAME canonical order :func:`driftless.assess.feed.attention_feed`
produces — text and HTML views of the same items, never re-ranked or
re-filtered — then sends over stdlib ``smtplib`` against an operator-supplied
SMTP relay (env vars below). No paid service is named or assumed; the free
default is a relay already on the host (local Postfix/Exim), documented in
``OPERATIONS.md``.

Rendering is a pure function of ``session`` and ``as_of`` — the same as-of
renders byte-identical text and HTML every time (see
``tests/test_notify_digest.py``). ``EmailSubscription.last_sent_as_of`` is the
cursor: it advances only once ``smtplib`` has accepted the message, so a
failed send leaves the next run resending the same as-of rather than skipping
it silently.

The recipient address is ``User.email`` when set; a user with no email but an
``@``-shaped ``username`` falls back to that, for stores created before the
email column existed. A user with neither is skipped, never sent to and never
a silent drop — the skip is named in every caller's output (see
``DigestResult.reason``).
"""

from __future__ import annotations

import os
import smtplib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.assess.feed import AttentionItem, attention_feed
from driftless.models.auth import User
from driftless.models.notify import EmailSubscription


def render_text(items: Iterable[AttentionItem], as_of: date) -> str:
    """The digest as plain text — the feed's order, verbatim."""
    items = list(items)
    lines = [f"Driftless attention digest -- as of {as_of.isoformat()}", ""]
    if not items:
        lines.append("Nothing needs attention.")
    for item in items:
        lines.append(f"[{item.severity.upper()}] {item.project_name}: {item.description}")
        lines.append(f"    -> {item.action}")
    return "\n".join(lines) + "\n"


def render_html(items: Iterable[AttentionItem], as_of: date) -> str:
    """The digest as HTML — same items, same order, as an unordered list."""
    items = list(items)
    rows = "".join(
        f"<li><strong>[{item.severity.upper()}] {item.project_name}</strong>: "
        f"{item.description}<br>&rarr; {item.action}</li>"
        for item in items
    )
    body = rows or "<p>Nothing needs attention.</p>"
    return (
        "<html><body>"
        f"<h1>Driftless attention digest &mdash; as of {as_of.isoformat()}</h1>"
        f"<ul>{body}</ul>"
        "</body></html>"
    )


def _smtp_settings() -> tuple[str, int, str, bool]:
    host = os.environ.get("DRIFTLESS_SMTP_HOST")
    if not host:
        raise SystemExit("error: DRIFTLESS_SMTP_HOST not set — no SMTP relay configured")
    port = int(os.environ.get("DRIFTLESS_SMTP_PORT", "25"))
    from_addr = os.environ.get("DRIFTLESS_SMTP_FROM", "driftless@localhost")
    starttls = os.environ.get("DRIFTLESS_SMTP_STARTTLS", "0") == "1"
    return host, port, from_addr, starttls


def send(
    to_addr: str,
    as_of: date,
    text: str,
    html: str,
    *,
    smtp_cls: type[smtplib.SMTP] | None = None,
) -> None:
    """Send one digest message over stdlib ``smtplib``; no third-party client."""
    host, port, from_addr, starttls = _smtp_settings()
    message = EmailMessage()
    message["Subject"] = f"Driftless attention digest -- {as_of.isoformat()}"
    message["From"] = from_addr
    message["To"] = to_addr
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    cls = smtp_cls or smtplib.SMTP
    with cls(host, port) as smtp:
        if starttls:
            smtp.starttls()
        user = os.environ.get("DRIFTLESS_SMTP_USER")
        password = os.environ.get("DRIFTLESS_SMTP_PASSWORD")
        if user and password:
            smtp.login(user, password)
        smtp.send_message(message)


def due(session: Session, as_of: date) -> list[EmailSubscription]:
    """Subscriptions not yet sent a digest for ``as_of`` — a cursor read, no send."""
    subs = session.scalars(select(EmailSubscription)).all()
    return [s for s in subs if s.last_sent_as_of is None or s.last_sent_as_of < as_of]


def recipient_address(user: User) -> str | None:
    """``user.email`` when set; an ``@``-shaped ``username`` as a fallback; else ``None``.

    ``None`` means the caller has no address to send to — the caller's job to skip
    and name, never this function's to invent one.
    """
    if user.email:
        return user.email
    if "@" in user.username:
        return user.username
    return None


@dataclass(frozen=True)
class DigestResult:
    subscription_id: int
    sent: bool
    #: Set only when the send was skipped for lack of a usable address — never for
    #: a dry run, which reports ``sent=False`` with no reason.
    reason: str | None = None


def run_digest(
    session: Session,
    as_of: date,
    *,
    dry_run: bool = False,
    smtp_cls: type[smtplib.SMTP] | None = None,
) -> list[DigestResult]:
    """Send (or, dry-run, merely report) the digest to every subscription due.

    The feed is rendered ONCE for every recipient at this ``as_of`` — one
    canonical body, addressed differently — not re-rendered per subscriber.
    """
    items = attention_feed(session, as_of)
    text = render_text(items, as_of)
    html = render_html(items, as_of)
    results = []
    for sub in due(session, as_of):
        to_addr = recipient_address(sub.user)
        if to_addr is None:
            reason = f"no email address for user {sub.user.username!r}"
            results.append(DigestResult(sub.id, sent=False, reason=reason))
            continue
        if dry_run:
            results.append(DigestResult(sub.id, sent=False))
            continue
        send(to_addr, as_of, text, html, smtp_cls=smtp_cls)
        sub.last_sent_as_of = as_of
        session.commit()
        results.append(DigestResult(sub.id, sent=True))
    return results
