"""Webhook delivery: the cursor, the signature, and the stop-at-first-failure rule."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import ChangeLog, register_changelog, set_actor
from driftless.models.notify import WebhookSubscription
from driftless.notify.delivery import deliver_all, pending

SECRET = "s3kret"  # pragma: allowlist secret


class _Received:
    def __init__(self) -> None:
        self.requests: list[tuple[bytes, str]] = []
        self.status = 200


def _handler(seen: _Received) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.requests.append((body, self.headers.get("X-Driftless-Signature", "")))
            self.send_response(seen.status)
            self.end_headers()

    return Handler


@pytest.fixture
def stub() -> Iterator[tuple[str, _Received]]:
    seen = _Received()
    server = HTTPServer(("127.0.0.1", 0), _handler(seen))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", seen
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'notify.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as session:
        set_actor(session, "jp")
        yield session


_ROWS = (("business", "insert"), ("project", "insert"), ("task", "insert"))


def _sub(
    db: Session, events: str, rows: int, url: str = "https://example.test/hook"
) -> WebhookSubscription:
    for table_name, operation in _ROWS[:rows]:
        db.add(ChangeLog(table_name=table_name, row_id="1", operation=operation))
    sub = WebhookSubscription(url=url, secret=SECRET, events=events)
    db.add(sub)
    db.commit()
    return sub


def test_dry_run_lists_pending_events_and_advances_no_cursor(db: Session) -> None:
    sub = _sub(db, "business,project", rows=2)
    results = deliver_all(db, dry_run=True)
    assert [(r.subscription_id, r.delivered, r.remaining) for r in results] == [(sub.id, 0, 2)]
    db.expire_all()
    assert db.get_one(WebhookSubscription, sub.id).last_delivered_changelog_id == 0


@pytest.mark.parametrize(("status", "delivered", "remaining"), [(200, 2, 0), (500, 0, 2)])
def test_delivery_advances_the_cursor_only_on_2xx(
    db: Session, stub: tuple[str, _Received], status: int, delivered: int, remaining: int
) -> None:
    url, seen = stub
    seen.status = status
    sub = _sub(db, "business,project", rows=2, url=url)
    results = deliver_all(db)
    assert [(r.subscription_id, r.delivered, r.remaining) for r in results] == [
        (sub.id, delivered, remaining)
    ]
    db.expire_all()
    where = ChangeLog.table_name.in_(["business", "project"])
    rows = list(db.scalars(select(ChangeLog).where(where).order_by(ChangeLog.id)))
    expected_cursor = rows[delivered - 1].id if delivered else 0
    assert db.get_one(WebhookSubscription, sub.id).last_delivered_changelog_id == expected_cursor
    assert len(seen.requests) == (delivered or 1)
    for body, signature in seen.requests:
        expected = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        assert signature == expected
        assert json.dumps(json.loads(body), sort_keys=True).encode() == body


def test_events_filter_admits_only_named_tables(db: Session) -> None:
    sub = _sub(db, "business,task", rows=3)
    matched = pending(db, sub)
    assert [row.table_name for row in matched] == ["business", "task"]
