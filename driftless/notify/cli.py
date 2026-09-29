"""The ``driftless notify`` command: subscribe a URL, list, deliver pending
events, and email an attention-list digest."""

from __future__ import annotations

import argparse
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.assess.feed import attention_feed
from driftless.db import new_engine, new_session_factory
from driftless.db.changelog import register_changelog, set_actor, set_via
from driftless.db.config import database_url
from driftless.models.notify import WebhookSubscription
from driftless.notify.delivery import ACTOR, deliver_all
from driftless.notify.digest import render_text, run_digest


def _open(db_url: str | None) -> Session:
    url = db_url or database_url()
    if not url:
        raise SystemExit("error: no database URL — pass --db-url or set DRIFTLESS_DATABASE_URL")
    factory = new_session_factory(new_engine(url))
    register_changelog(factory)  # a subscription add, and every cursor advance, is audited
    session = factory()
    set_actor(session, ACTOR)
    set_via(session, "cli")
    return session


def _run_add(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        session.add(WebhookSubscription(url=args.url, secret=args.secret, events=args.events))
        session.commit()
    return 0


def _run_list(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        for sub in session.scalars(select(WebhookSubscription).order_by(WebhookSubscription.id)):
            state = "active" if sub.active else "disabled"
            print(
                f"{sub.id:<5} {sub.url:40} {sub.events:20} {state:9} cursor={sub.last_delivered_changelog_id}"
            )
    return 0


def _run_deliver(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        for result in deliver_all(session, dry_run=args.dry_run):
            label = "pending" if args.dry_run else f"delivered {result.delivered}; pending"
            print(f"subscription {result.subscription_id}: {label} {result.remaining}")
    return 0


def _run_digest(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        if args.dry_run:
            print(render_text(attention_feed(session, args.as_of), args.as_of), end="")
        for result in run_digest(session, args.as_of, dry_run=args.dry_run):
            if result.reason is not None:
                label = f"skipped ({result.reason})"
            else:
                label = "would send" if args.dry_run else "sent"
            print(f"subscription {result.subscription_id}: {label}")
    return 0


def add_notify_subparser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    notify = commands.add_parser(
        "notify", help="subscribe a URL/user, list, deliver pending events, email a digest"
    )
    sub = notify.add_subparsers(dest="notify_command", required=True)
    add = sub.add_parser("add", help="subscribe a URL to ChangeLog events")
    add.add_argument("--url", required=True)
    add.add_argument("--secret", required=True)
    add.add_argument("--events", default="*")
    listing = sub.add_parser("list", help="list subscriptions, their state and cursor")
    deliver = sub.add_parser("deliver", help="deliver pending events to every active subscription")
    deliver.add_argument("--dry-run", action="store_true")
    digest = sub.add_parser(
        "digest", help="email the attention-list digest to every subscription due"
    )
    digest.add_argument("--as-of", type=date.fromisoformat, required=True)
    digest.add_argument("--dry-run", action="store_true")
    leaves = ((add, _run_add), (listing, _run_list), (deliver, _run_deliver), (digest, _run_digest))
    for parser, handler in leaves:
        parser.add_argument("--db-url", default=None)
        parser.set_defaults(handler=handler)
