"""The sign-off ledger names the signer the GATE resolved, never the one the caller typed.

The ledger's whole value is that it is an append-only record of who approved what, and
``signed_by`` used to be an ordinary request field: a contributor could POST
``signed_by="CFO"`` — or edit the hidden form input on ``/threats`` — and land a permanent
row naming an approver who never approved. Append-only made it worse, not better: the
forged row can never be removed.

So the same rule the ChangeLog actor already follows applies here. When the gate resolved a
principal, the server stamps that name and the request's own value is discarded — the shape
``StatusSnapshot`` already uses for ``percent_complete`` (stamped from calc, never accepted
from the request). It is an overwrite rather than a 4xx on purpose: both browser forms
always post the field, so refusing a supplied name would break every real sign-off from the
UI, and the 201 body echoes the name that was actually stored, so no caller is misled.

What is deliberately KEPT is the on-behalf-of write: the shared ``DRIFTLESS_API_TOKEN``
bearer resolves no principal by design (``secure.py`` — the bootstrap credential), so an
importer or an agent recording a decision a named human made offline still supplies the
name. Nothing else can.

These tests refuse to inject either half of the seam: a real user signs in through the real
login handler behind a real ``TokenGate``, and the row is read back out of the store.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from driftless.api import app as app_module
from driftless.api.app import app
from driftless.api.secure import TokenGate
from driftless.auth import sessions
from driftless.auth.passwords import hash_password
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.models import SignOff, User
from driftless.web import csrf

TOKEN = "deployment-bearer-token"  # pragma: allowlist secret  (in-test gate token)
SECRET = "test-signing-secret"  # pragma: allowlist secret  (throwaway in-test signing key)
PASSWORD = "correct horse battery"  # pragma: allowlist secret  (throwaway in-test password)
USERNAME = "jp"
CLAIMED = "CFO"  # the name the caller types, and the one that must never reach a row
SUBJECT = "cost:project:1"


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    """A throwaway store wired in as the app's OWN lazy factory, holding one contributor.

    Same shape as ``tests/test_audit_actor.py``: the gate's default session scope is the
    API's own factory, so a user who exists only here proves the gate and the routes share
    one factory. A file rather than in-memory, because ``TestClient`` serves each request
    on another thread.
    """
    engine = new_engine(f"sqlite:///{tmp_path / 'signoff.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    monkeypatch.setattr(app_module, "_factory", factory)
    monkeypatch.setenv(sessions.SECRET_ENV, SECRET)
    monkeypatch.setenv(sessions.SECURE_ENV, "0")  # a plain-http TestClient keeps the cookie
    with factory() as db:
        db.add(User(username=USERNAME, password_hash=hash_password(PASSWORD), role="contributor"))
        db.commit()
    yield factory


def _signers(factory: sessionmaker[Session]) -> list[str]:
    with factory() as db:
        return [row.signed_by for row in db.scalars(select(SignOff).order_by(SignOff.id))]


def _signed_in() -> TestClient:
    """A browser that signed in for real: real gate, real login handler, real cookie."""
    client = TestClient(TokenGate(app, TOKEN), follow_redirects=False)
    form = client.get("/login")
    field = re.search(r'name="csrf_token" value="([^"]+)"', form.text)
    assert field is not None, "the login form rendered no CSRF token to post back"
    body = {"username": USERNAME, "password": PASSWORD, "csrf_token": field.group(1)}
    posted = client.post("/login", data=body)
    assert posted.status_code == 303, f"sign-in was refused ({posted.status_code}): {posted.text}"
    return client


def test_the_json_route_records_the_signed_in_user_not_the_claimed_name(
    store: sessionmaker[Session],
) -> None:
    """``POST /sign-offs`` as ``jp`` claiming ``CFO`` lands a row signed by ``jp``."""
    client = _signed_in()

    created = client.post(
        "/sign-offs",
        json={
            "subject_kind": "threat",
            "subject_ref": SUBJECT,
            "decision": "accepted",
            "signed_by": CLAIMED,
        },
    )

    assert created.status_code == 201, created.text
    assert _signers(store) == [USERNAME], (
        "the ledger recorded the name the caller typed — an authenticated user can "
        "attribute a permanent, un-deletable approval to somebody else"
    )
    assert created.json()["signed_by"] == USERNAME, "the response must not echo the claim back"


def test_the_web_form_records_the_signed_in_user_not_the_posted_field(
    store: sessionmaker[Session],
) -> None:
    """The same rule from the browser: the ``signed_by`` input is a claim, not the record."""
    client = _signed_in()
    board = client.get("/threats")
    assert board.status_code == 200, board.text

    posted = client.post(
        "/sign-off",
        data={
            "subject_kind": "threat",
            "subject_ref": SUBJECT,
            "decision": "accepted",
            "signed_by": CLAIMED,
            csrf.FIELD: client.cookies[csrf.COOKIE],
        },
    )

    assert posted.status_code == 303, posted.text
    assert _signers(store) == [USERNAME], (
        "the hidden form field decided the ledger's signer — editing one input in the "
        "browser forges a permanent approval in somebody else's name"
    )


def test_the_shared_bearer_keeps_the_supplied_name(store: sessionmaker[Session]) -> None:
    """DECIDED, and kept: the bootstrap bearer resolves NO principal (``secure.py``), so the
    supplied name is the only signer available — the on-behalf-of write an importer or an
    agent uses to record a decision a named human made offline. Overwriting it with a
    fabricated name, or refusing it, would delete the only legitimate use of the field."""
    client = TestClient(TokenGate(app, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})

    created = client.post(
        "/sign-offs",
        json={
            "subject_kind": "threat",
            "subject_ref": SUBJECT,
            "decision": "accepted",
            "signed_by": "Fiona Offline",
        },
    )

    assert created.status_code == 201, created.text
    assert _signers(store) == ["Fiona Offline"]
