"""The gate logs its own refusals: :class:`~driftless.api.secure.TokenGate` answers a
401 or a 403 directly, without ever calling inward — so the request log
(``driftless.api.logging``) and the metrics middleware (``driftless.api.metrics``),
both installed *inside* the gate, never see a refused request at all. A burst of
rejected credentials is otherwise indistinguishable from no traffic whatsoever.

This pins the fix at the one place that actually sees the refusal: the gate itself,
on its own existing ``driftless.secure`` logger, at INFO — a refusal is ordinary,
expected traffic (a scanner, a stale client, a viewer clicking a write button they
cannot use), not an application error, so it does not deserve the WARNING level this
module already reserves for genuine misconfiguration (an unreadable route table, a
deployment running open).

Never the token, never the header, never a hash of either — see
``driftless/api/logging.py``'s rule, which this file's records must honour just as
strictly. The single most important test below asserts that positively, over every
distinguishable secret value exercised elsewhere in this file.
"""

import json
import logging
from collections.abc import Iterator
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api import secure
from driftless.api.app import app, get_session
from driftless.auth import sessions
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import User

LOGGER = "driftless.secure"
TOKEN = "s3cr3t-gate-token"  # pragma: allowlist secret  (throwaway in-test bearer)
MINTED_SECRET_MARKER = "sh0uldNeverBeLogged"  # pragma: allowlist secret
COOKIE_SECRET_MARKER = "c00ki3ShouldNeverBeLogged"  # pragma: allowlist secret
SIGNING_SECRET = "test-signing-secret"  # pragma: allowlist secret  (throwaway in-test key)
API_WRITE = "/projects"  # a JSON write route, never a page
GATED_READ = "/health/ready"  # gated, and not one of the app's HTML page routes


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    # A file, not in-memory: TestClient serves the request on another thread.
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        app.dependency_overrides[get_session] = lambda: session
        yield session
        app.dependency_overrides.clear()


@pytest.fixture
def signed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(sessions.SECRET_ENV, SIGNING_SECRET)


def _user(db: Session, *, role: str = "viewer", username: str = "jp") -> User:
    user = User(username=username, password_hash="x", role=role, is_active=True, session_epoch=0)
    db.add(user)
    db.commit()
    return user


def _cookie_header(value: str) -> dict[str, str]:
    return {"Cookie": f"{sessions.COOKIE}={value}"}


def _issued(user: User) -> str:
    expires = datetime.now(UTC) + timedelta(hours=1)
    return sessions.issue(user.id, user.username, user.role, expires, SIGNING_SECRET, 0)


def _gate(db: Session) -> secure.TokenGate:
    """The gate reading the test's own session -- never the module's default lazy
    factory, which would open an unrelated file this test never created a schema in."""
    return secure.TokenGate(app, TOKEN, session_scope=lambda: nullcontext(db))


def _refusal_lines(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    """Every JSON refusal record the gate emitted, parsed. Skips the module's other
    lines (the dev-mode and unreadable-route-table warnings), which are plain text."""
    lines = []
    for record in caplog.records:
        if record.name != LOGGER:
            continue
        try:
            payload = json.loads(record.getMessage())
        except (json.JSONDecodeError, TypeError):
            continue
        if payload.get("event") == "refused":
            lines.append(payload)
    return lines


def test_an_unauthenticated_request_emits_a_refusal_record(
    db: Session, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    gate = _gate(db)
    resp = TestClient(gate, follow_redirects=False).get(GATED_READ)
    assert resp.status_code == 401

    (line,) = _refusal_lines(caplog)
    assert line["method"] == "GET"
    assert line["path"] == GATED_READ
    assert line["reason"] == "unauthenticated"


def test_an_unauthorized_write_emits_a_distinguishable_refusal_record(
    db: Session, signed: None, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    user = _user(db, role="viewer", username="viewer-jp")
    gate = _gate(db)
    resp = TestClient(gate, follow_redirects=False).post(
        API_WRITE, headers=_cookie_header(_issued(user)), json={}
    )
    assert resp.status_code == 403

    (line,) = _refusal_lines(caplog)
    assert line["method"] == "POST"
    assert line["path"] == API_WRITE
    assert line["reason"] == "insufficient_role"
    assert line["reason"] != "unauthenticated"  # distinguishable from the 401 case


def test_no_credential_material_ever_reaches_the_log(
    db: Session, signed: None, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    gate = _gate(db)
    client = TestClient(gate, follow_redirects=False)

    # A wrong bearer, refused as a 401.
    client.get(GATED_READ, headers={"Authorization": f"Bearer {MINTED_SECRET_MARKER}"})
    # A forged/garbage cookie, refused as a 401.
    client.get(GATED_READ, headers=_cookie_header(COOKIE_SECRET_MARKER))
    # A live, correctly-signed cookie, refused as a 403 (insufficient role).
    viewer = _user(db, role="viewer", username="viewer-jp")
    client.post(API_WRITE, headers=_cookie_header(_issued(viewer)), json={})
    # The shared bootstrap token itself, presented correctly, must never appear either
    # -- an allowed request logs nothing, but this proves a 401 branch alongside it
    # cannot have leaked it via some other path.
    client.get("/health", headers={"Authorization": f"Bearer {TOKEN}"})

    assert len(_refusal_lines(caplog)) == 3  # the three refusals above, not the health probe

    emitted = "\n".join(r.getMessage() for r in caplog.records if r.name == LOGGER)
    assert MINTED_SECRET_MARKER not in emitted
    assert COOKIE_SECRET_MARKER not in emitted
    assert TOKEN not in emitted
    assert "authorization" not in emitted.lower()
    assert "cookie" not in emitted.lower()


def test_an_allowed_request_emits_no_refusal_record(
    db: Session, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    gate = _gate(db)
    # A route the route table actually answers, unlike /health/ready, which 503s
    # against a plain `create_all` schema with no alembic revision stamped.
    resp = TestClient(gate).get("/businesses", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200
    assert _refusal_lines(caplog) == []
