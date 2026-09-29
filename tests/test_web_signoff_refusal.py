"""``POST /sign-off`` refuses a bad field as 422, never a 500.

``sign_off()`` builds ``SignOffIn`` straight from the posted form fields with no
try/except, so a bad ``decision`` or ``subject_kind`` reached pydantic's own
``ValidationError`` — not an ``HTTPException`` — and fell through every layer to
the catch-all 500 handler. ``status_submit`` next door (``/projects/{id}/status``)
already wraps its own ``StatusSnapshotIn`` construction in
``except ValidationError: raise HTTPException(422, ...)`` — this test pins
``/sign-off`` to that same, already-established in-file pattern.

Same fixture shape as ``tests/test_signoff_signer.py``: a file-backed store wired
in as the app's own lazy factory, one admin user, and a real sign-in through the
real login handler so the CSRF pair is genuine.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from driftless.api.app import app, get_session
from driftless.auth import sessions
from driftless.auth.passwords import hash_password
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.models import SignOff, User
from driftless.web import csrf

SECRET = "test-signing-secret"  # pragma: allowlist secret  (throwaway in-test signing key)
PASSWORD = "correct horse battery"  # pragma: allowlist secret  (throwaway in-test password)
USERNAME = "jp"
SUBJECT = "cost:project:1"


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    """A throwaway store, holding one admin, wired in through the app's PUBLIC seam.

    ``admin``, not ``contributor``: the sign-off ledger is gated to admin alone.
    A file rather than in-memory, because ``TestClient`` serves each request on
    another thread.

    Overriding the ``get_session`` dependency rather than monkeypatching the module
    global the sibling tests reach for: that global is private, and it is being moved
    out of ``driftless.api.app`` into ``driftless.db.session`` in a concurrent change,
    which would turn ``monkeypatch.setattr(app_module, "_factory", …)`` into an
    ``AttributeError`` here the moment the two land together. ``get_session`` is the
    declared seam every route already takes, so this wiring does not care where the
    factory ends up living.
    """
    engine = new_engine(f"sqlite:///{tmp_path / 'signoff.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)

    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    monkeypatch.setenv(sessions.SECRET_ENV, SECRET)
    monkeypatch.setenv(sessions.SECURE_ENV, "0")  # a plain-http TestClient keeps the cookie
    with factory() as db:
        db.add(User(username=USERNAME, password_hash=hash_password(PASSWORD), role="admin"))
        db.commit()
    yield factory
    app.dependency_overrides.pop(get_session, None)  # the app object is module-global


def _row_count(factory: sessionmaker[Session]) -> int:
    with factory() as db:
        return len(db.scalars(select(SignOff)).all())


def _signed_in() -> TestClient:
    """A browser that signed in for real: real gate, real login handler, real cookie.

    ``raise_server_exceptions=False`` is load-bearing here: with the default
    ``True`` an unhandled exception re-raises through the test client instead of
    answering with the status a real ASGI server would send, so a 500 defect
    would surface as a traceback rather than the status this test asserts on.
    """
    client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
    form = client.get("/login")
    field = re.search(r'name="csrf_token" value="([^"]+)"', form.text)
    assert field is not None, "the login form rendered no CSRF token to post back"
    body = {"username": USERNAME, "password": PASSWORD, "csrf_token": field.group(1)}
    posted = client.post("/login", data=body)
    assert posted.status_code == 303, f"sign-in was refused ({posted.status_code}): {posted.text}"
    return client


def test_a_bad_decision_is_refused_422_not_500(store: sessionmaker[Session]) -> None:
    client = _signed_in()
    board = client.get("/threats")  # mints the CSRF cookie the post below sends back
    assert board.status_code == 200, board.text

    posted = client.post(
        "/sign-off",
        data={
            "subject_kind": "threat",
            "subject_ref": SUBJECT,
            "decision": "not-a-real-decision",
            csrf.FIELD: client.cookies[csrf.COOKIE],
        },
    )

    assert posted.status_code == 422, posted.text
    assert _row_count(store) == 0, "a refused post must not land a ledger row"


def test_a_bad_subject_kind_is_refused_422_not_500(store: sessionmaker[Session]) -> None:
    client = _signed_in()
    board = client.get("/threats")  # mints the CSRF cookie the post below sends back
    assert board.status_code == 200, board.text

    posted = client.post(
        "/sign-off",
        data={
            "subject_kind": "not-a-real-kind",
            "subject_ref": SUBJECT,
            "decision": "accepted",
            csrf.FIELD: client.cookies[csrf.COOKIE],
        },
    )

    assert posted.status_code == 422, posted.text
    assert _row_count(store) == 0, "a refused post must not land a ledger row"
