"""Every audited write is credited to the signed-in user, across the whole seam.

The identity is resolved once per request by the gate, and the audit row is written
by a flush listener that reads it off the session — two halves that each passed
their own tests while every ChangeLog row in production carried ``actor=None``,
because nothing joined them. So these tests refuse to inject either half: a real
user signs in through the real login handler, behind a real ``TokenGate`` built
with no ``session_scope`` argument, and the row is read back out of the store.

That last detail is load-bearing twice over. The gate's default scope is the API's
own lazy factory, so a signed-in user who exists ONLY in this test's store proves
the gate and the routes share one factory — a second engine here would resolve no
principal and answer 401. And the routes are driven through the real
``get_session``: the usual ``dependency_overrides`` fixture replaces the very
dependency that stamps the credit, so an overridden test is structurally blind to
this property.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, get_args, get_type_hints

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from driftless.api.app import app, get_session
from driftless.api.secure import TokenGate
from driftless.auth import sessions
from driftless.auth.passwords import hash_password
from driftless.db import Base, new_engine, new_session_factory
from driftless.db import session as db_session
from driftless.db.changelog import ChangeLog, register_changelog
from driftless.models import User

TOKEN = "deployment-bearer-token"  # pragma: allowlist secret  (in-test gate token)
SECRET = "test-signing-secret"  # pragma: allowlist secret  (throwaway in-test signing key)
PASSWORD = "correct horse battery"  # pragma: allowlist secret  (throwaway in-test password)
USERNAME = "jp"
_TOKEN_FIELD = re.compile(r'name="csrf_token" value="([^"]+)"')


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    """A throwaway store wired in as the app's OWN lazy factory.

    ``monkeypatch.setattr`` rather than a bare assignment, so the module global is
    restored and a later test in the same session is not left writing here. The
    changelog listener is registered exactly as ``session_scope`` does for the real
    factory. A file rather than in-memory, because ``TestClient`` serves each
    request on another thread.
    """
    engine = new_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    monkeypatch.setattr(db_session, "_factory", factory)
    monkeypatch.setenv(sessions.SECRET_ENV, SECRET)
    monkeypatch.setenv(sessions.SECURE_ENV, "0")  # a plain-http TestClient keeps the cookie
    with factory() as db:
        db.add(User(username=USERNAME, password_hash=hash_password(PASSWORD), role="contributor"))
        db.commit()
    yield factory


def _actors(factory: sessionmaker[Session], table: str) -> list[str | None]:
    with factory() as db:
        query = select(ChangeLog).where(ChangeLog.table_name == table).order_by(ChangeLog.id)
        return [row.actor for row in db.scalars(query)]


def _signed_in() -> TestClient:
    """A browser that signed in for real: real gate, real login handler, real cookie."""
    client = TestClient(TokenGate(app, TOKEN), follow_redirects=False)
    form = client.get("/login")
    field = _TOKEN_FIELD.search(form.text)
    assert field is not None, "the login form rendered no CSRF token to post back"
    body = {"username": USERNAME, "password": PASSWORD, "csrf_token": field.group(1)}
    posted = client.post("/login", data=body)
    assert posted.status_code == 303, f"sign-in was refused ({posted.status_code}): {posted.text}"
    return client


def test_a_signed_in_users_write_is_credited_to_them(store: sessionmaker[Session]) -> None:
    """The seam end to end: cookie -> principal -> session actor -> ChangeLog row."""
    client = _signed_in()

    created = client.post("/businesses", json={"name": "Back Road Creative"})

    assert created.status_code == 201, created.text
    assert _actors(store, "business") == [USERNAME], (
        "the write landed unattributed — the signed-in user the gate resolved never "
        "reached the session the changelog listener reads its actor from"
    )


def test_a_bearer_only_write_is_recorded_as_unattributed(store: sessionmaker[Session]) -> None:
    """DECIDED, and stated honestly rather than faked: the shared bearer token resolves
    no principal, so its writes stay ``actor=None`` like a CLI or migration write.
    ``DRIFTLESS_API_TOKEN`` is the bootstrap credential; per-user API tokens are their
    own unit. Inventing an actor here would put a name on a row nobody signed."""
    client = TestClient(TokenGate(app, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})

    created = client.post("/businesses", json={"name": "Bootstrap Write"})

    assert created.status_code == 201, created.text
    assert _actors(store, "business") == [None]


def _yields_a_session(call: Callable[..., Any] | None) -> bool:
    if call is None:
        return False
    try:
        hints = get_type_hints(call)
    except Exception:  # an unresolvable annotation is not a session provider
        return False
    return Session in get_args(hints.get("return"))


def _flat_dependencies(dependant: Any) -> Iterator[Any]:
    """Every dependency in a route's tree, including nested ones.

    FastAPI ships ``get_flat_dependant`` for this, but it lives in the private
    ``fastapi.dependencies.utils`` module and stopped being importable there in
    0.140. ``pyproject`` declares ``fastapi>=0.110`` with no upper bound, so a
    fresh resolve breaks the import. The walk is four lines; owning it keeps
    this test off a private API instead of pinning the framework backwards.
    """
    for dep in dependant.dependencies:
        yield dep
        yield from _flat_dependencies(dep)


def test_no_route_reaches_the_store_except_through_the_credited_dependency() -> None:
    """One chokepoint, so a write site cannot forget the credit — it never asks for it.

    Every registered route obtains its session from ``get_session``, which is where
    the actor is stamped. A router added later that wired its own session provider
    would write unattributed rows on a path no test of *its* own would notice; it
    fails here instead, against the app as actually assembled.
    """
    providers = {
        dep.call
        for route in app.routes
        if isinstance(route, APIRoute)
        for dep in _flat_dependencies(route.dependant)
        if _yields_a_session(dep.call)
    }

    assert providers == {get_session}
