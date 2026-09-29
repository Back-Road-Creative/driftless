"""Deliver pending ``ChangeLog`` rows to each active subscription; stdlib only."""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.db.changelog import ChangeLog
from driftless.models.notify import WebhookSubscription

ACTOR = "system:notify"


def pending(session: Session, subscription: WebhookSubscription) -> list[ChangeLog]:
    events = subscription.events
    rows = session.scalars(
        select(ChangeLog)
        .where(ChangeLog.id > subscription.last_delivered_changelog_id)
        .order_by(ChangeLog.id)
    ).all()
    return [row for row in rows if events == "*" or row.table_name in events.split(",")]


def _post(url: str, secret: str, row: ChangeLog) -> bool:
    body = json.dumps(
        {
            "id": row.id,
            "table_name": row.table_name,
            "row_id": row.row_id,
            "operation": row.operation,
            "changed_at": row.changed_at.isoformat(),
            "actor": row.actor,
            "detail": json.loads(row.detail),
        },
        sort_keys=True,
    ).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Driftless-Signature": sig}
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return bool(200 <= response.status < 300)
    except (urllib.error.HTTPError, urllib.error.URLError):
        return False


@dataclass(frozen=True)
class DeliveryResult:
    subscription_id: int
    delivered: int
    remaining: int


def deliver_one(
    session: Session, subscription: WebhookSubscription, *, dry_run: bool = False
) -> DeliveryResult:
    events = pending(session, subscription)
    if dry_run:
        return DeliveryResult(subscription.id, delivered=0, remaining=len(events))
    delivered = 0
    for row in events:
        if not _post(subscription.url, subscription.secret, row):
            break
        subscription.last_delivered_changelog_id = row.id
        session.commit()
        delivered += 1
    return DeliveryResult(subscription.id, delivered=delivered, remaining=len(events) - delivered)


def deliver_all(session: Session, *, dry_run: bool = False) -> list[DeliveryResult]:
    subs = session.scalars(select(WebhookSubscription).where(WebhookSubscription.active.is_(True)))
    return [deliver_one(session, sub, dry_run=dry_run) for sub in subs]
