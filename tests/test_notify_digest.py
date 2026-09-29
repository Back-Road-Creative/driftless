"""The email digest: deterministic rendering and a cursor that only advances on
a successful send. ``smtplib`` is stubbed throughout — no network."""

from __future__ import annotations

import smtplib
from collections.abc import Iterator
from datetime import date
from email.message import EmailMessage
from pathlib import Path
from types import TracebackType

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.assess.feed import AttentionItem
from driftless.cli import main
from driftless.db import Base, new_engine, new_session_factory
from driftless.models.notify import EmailSubscription
from driftless.notify.digest import due, render_html, render_text, run_digest, send

AS_OF = date(2026, 3, 31)


class _FakeSMTP(smtplib.SMTP):
    """Records every message it was asked to send; never touches the network.

    Subclasses ``smtplib.SMTP`` only so it satisfies ``run_digest``'s
    ``type[smtplib.SMTP]`` parameter -- ``__init__`` deliberately skips the
    real base class, which would otherwise open a socket.
    """

    sent: list[tuple[str, str, str]] = []  # (host, to, subject) -- class-level, reset per test
    logins: list[tuple[str, str]] = []
    starttls_calls = 0

    def __init__(self, host: str, port: int) -> None:  # no super().__init__: no real socket
        self.host = host
        self.port = port

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def starttls(self, **kwargs: object) -> tuple[int, bytes]:
        type(self).starttls_calls += 1
        return 220, b"ok"

    def login(self, user: str, password: str, **kwargs: object) -> tuple[int, bytes]:
        type(self).logins.append((user, password))
        return 235, b"ok"

    def send_message(  # type: ignore[override]
        self, msg: EmailMessage, *args: object, **kwargs: object
    ) -> dict[str, tuple[int, bytes]]:
        subject = str(msg["Subject"])
        to = str(msg["To"])
        type(self).sent.append((self.host, to, subject))
        return {}


@pytest.fixture(autouse=True)
def _reset_fake_smtp() -> Iterator[None]:
    _FakeSMTP.sent = []
    _FakeSMTP.logins = []
    _FakeSMTP.starttls_calls = 0
    yield


@pytest.fixture(autouse=True)
def _smtp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRIFTLESS_SMTP_HOST", "mail.example.test")
    monkeypatch.setenv("DRIFTLESS_SMTP_FROM", "driftless@example.test")


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'digest.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def subscribed_user(db: Session) -> tuple[m.User, EmailSubscription]:
    user = m.User(username="pm@example.test", password_hash="x", role="viewer")
    sub = EmailSubscription(user=user, cadence="weekly")
    db.add(sub)
    db.commit()
    return user, sub


def test_render_text_is_byte_identical_across_repeat_renders(db: Session) -> None:
    from driftless.assess.feed import attention_feed

    items = attention_feed(db, AS_OF)
    assert render_text(items, AS_OF) == render_text(items, AS_OF)


def test_render_html_is_byte_identical_across_repeat_renders(db: Session) -> None:
    from driftless.assess.feed import attention_feed

    items = attention_feed(db, AS_OF)
    assert render_html(items, AS_OF) == render_html(items, AS_OF)


def test_render_text_with_no_attention_items(db: Session) -> None:
    from driftless.assess.feed import attention_feed

    text = render_text(attention_feed(db, AS_OF), AS_OF)
    assert "Nothing needs attention." in text
    assert AS_OF.isoformat() in text


def test_run_digest_sends_and_advances_the_cursor(
    db: Session, subscribed_user: tuple[m.User, EmailSubscription]
) -> None:
    _, sub = subscribed_user
    results = run_digest(db, AS_OF, smtp_cls=_FakeSMTP)
    assert [r.sent for r in results] == [True]
    assert sub.last_sent_as_of == AS_OF
    assert _FakeSMTP.sent == [
        ("mail.example.test", "pm@example.test", "Driftless attention digest -- 2026-03-31")
    ]


def test_run_digest_dry_run_neither_sends_nor_advances_the_cursor(
    db: Session, subscribed_user: tuple[m.User, EmailSubscription]
) -> None:
    _, sub = subscribed_user
    results = run_digest(db, AS_OF, dry_run=True, smtp_cls=_FakeSMTP)
    assert [r.sent for r in results] == [False]
    assert sub.last_sent_as_of is None
    assert _FakeSMTP.sent == []


def test_a_subscription_already_sent_for_this_as_of_is_not_due_again(
    db: Session, subscribed_user: tuple[m.User, EmailSubscription]
) -> None:
    _, sub = subscribed_user
    sub.last_sent_as_of = AS_OF
    db.commit()
    assert due(db, AS_OF) == []
    assert run_digest(db, AS_OF, smtp_cls=_FakeSMTP) == []
    assert _FakeSMTP.sent == []


def test_a_subscription_is_due_again_for_a_later_as_of(
    db: Session, subscribed_user: tuple[m.User, EmailSubscription]
) -> None:
    _, sub = subscribed_user
    sub.last_sent_as_of = AS_OF
    db.commit()
    later = date(2026, 4, 30)
    results = run_digest(db, later, smtp_cls=_FakeSMTP)
    assert [r.sent for r in results] == [True]
    assert sub.last_sent_as_of == later


def test_run_digest_prefers_the_email_column_over_the_username(db: Session) -> None:
    user = m.User(username="pm", email="pm-real@example.test", password_hash="x")
    sub = EmailSubscription(user=user, cadence="weekly")
    db.add(sub)
    db.commit()
    results = run_digest(db, AS_OF, smtp_cls=_FakeSMTP)
    assert [r.sent for r in results] == [True]
    assert _FakeSMTP.sent == [
        ("mail.example.test", "pm-real@example.test", "Driftless attention digest -- 2026-03-31")
    ]


def test_run_digest_falls_back_to_an_at_shaped_username_when_email_is_unset(
    db: Session,
) -> None:
    user = m.User(username="pm@example.test", password_hash="x")
    sub = EmailSubscription(user=user, cadence="weekly")
    db.add(sub)
    db.commit()
    results = run_digest(db, AS_OF, smtp_cls=_FakeSMTP)
    assert [r.sent for r in results] == [True]
    assert _FakeSMTP.sent == [
        ("mail.example.test", "pm@example.test", "Driftless attention digest -- 2026-03-31")
    ]


def test_run_digest_skips_a_user_with_neither_email_nor_an_at_shaped_username(
    db: Session,
) -> None:
    user = m.User(username="pm", password_hash="x")
    sub = EmailSubscription(user=user, cadence="weekly")
    db.add(sub)
    db.commit()
    results = run_digest(db, AS_OF, smtp_cls=_FakeSMTP)
    assert results[0].sent is False
    assert results[0].reason is not None and "pm" in results[0].reason
    assert sub.last_sent_as_of is None  # never advanced for a skipped recipient
    assert _FakeSMTP.sent == []


def test_missing_smtp_host_refuses_to_send(
    db: Session, subscribed_user: tuple[m.User, EmailSubscription], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DRIFTLESS_SMTP_HOST", raising=False)
    with pytest.raises(SystemExit):
        run_digest(db, AS_OF, smtp_cls=_FakeSMTP)


_ITEM = AttentionItem(
    id="threat:1",
    kind="threat",
    severity="red",
    score=0.9,
    description="GMS is over budget.",
    action="Re-estimate cost at completion.",
    project_id=1,
    project_name="GMS",
)


def test_render_text_lists_each_item_and_its_action() -> None:
    text = render_text([_ITEM], AS_OF)
    assert "[RED] GMS: GMS is over budget." in text
    assert "-> Re-estimate cost at completion." in text


def test_render_html_lists_each_item_and_its_action() -> None:
    html = render_html([_ITEM], AS_OF)
    assert "[RED] GMS" in html
    assert "Re-estimate cost at completion." in html


def test_send_upgrades_the_connection_and_authenticates_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DRIFTLESS_SMTP_STARTTLS", "1")
    monkeypatch.setenv("DRIFTLESS_SMTP_USER", "relay-user")
    monkeypatch.setenv("DRIFTLESS_SMTP_PASSWORD", "relay-pass")
    send("pm@example.test", AS_OF, "text body", "<p>html body</p>", smtp_cls=_FakeSMTP)
    assert _FakeSMTP.starttls_calls == 1
    assert _FakeSMTP.logins == [("relay-user", "relay-pass")]
    assert _FakeSMTP.sent == [
        ("mail.example.test", "pm@example.test", "Driftless attention digest -- 2026-03-31")
    ]


def test_cli_digest_dry_run_prints_the_body_and_reports_pending(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_url = f"sqlite:///{tmp_path / 'cli_digest.db'}"
    Base.metadata.create_all(new_engine(db_url))
    with new_session_factory(new_engine(db_url))() as session:
        session.add(EmailSubscription(user=m.User(username="pm@example.test", password_hash="x")))
        session.commit()
    assert main(["notify", "digest", "--as-of", "2026-03-31", "--dry-run", "--db-url", db_url]) == 0
    out = capsys.readouterr().out
    assert "Driftless attention digest -- as of 2026-03-31" in out
    assert "would send" in out


def test_cli_digest_reports_a_skipped_user_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_url = f"sqlite:///{tmp_path / 'cli_digest_skip.db'}"
    Base.metadata.create_all(new_engine(db_url))
    with new_session_factory(new_engine(db_url))() as session:
        session.add(EmailSubscription(user=m.User(username="pm", password_hash="x")))
        session.commit()
    assert main(["notify", "digest", "--as-of", "2026-03-31", "--db-url", db_url]) == 0
    out = capsys.readouterr().out
    assert "skipped" in out and "pm" in out
    assert _FakeSMTP.sent == []


def test_cli_digest_sends_over_the_stubbed_smtp_class(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("driftless.notify.digest.smtplib.SMTP", _FakeSMTP)
    db_url = f"sqlite:///{tmp_path / 'cli_digest_send.db'}"
    Base.metadata.create_all(new_engine(db_url))
    with new_session_factory(new_engine(db_url))() as session:
        session.add(EmailSubscription(user=m.User(username="pm@example.test", password_hash="x")))
        session.commit()
    assert main(["notify", "digest", "--as-of", "2026-03-31", "--db-url", db_url]) == 0
    assert "sent" in capsys.readouterr().out
    assert _FakeSMTP.sent == [
        ("mail.example.test", "pm@example.test", "Driftless attention digest -- 2026-03-31")
    ]
    with new_session_factory(new_engine(db_url))() as session:
        sub = session.get_one(EmailSubscription, 1)
        assert sub.last_sent_as_of == AS_OF
