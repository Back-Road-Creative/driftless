"""The whole sign-in walk against a gated deployment — the seam no unit test can see.

This is the property that spans PRs, and it is here because a per-unit gate is
structurally blind to it. #1610 (the request gate) and #1611 (the login wiring) each
shipped green — full suite, ruff, mypy — and together they were broken: #1610
originally gated ``/login`` itself, so with ``DRIFTLESS_API_TOKEN`` set a browser met
401 at the sign-in form and could never obtain the cookie the gate accepts. Neither
unit's tests could reach across the other's, so the defect was caught by hand, by
driving a browser end to end. That hand check is this file.

One client walks it in order: sent to the form with no credential, admitted to it,
issued a cookie by a correct password, admitted to a gated page by that cookie alone
with no bearer header, signed out, and refused when the captured cookie is replayed.
The last step is the load-bearing one — it proves the session epoch, logout's bump of
it and the gate's per-request ``principal.resolve`` compose into real revocation,
rather than three features that each look right alone.

A second client walks the *role* half of the same seam, for the same reason: a viewer
signs in through the real form, reads both surfaces, is refused a write — leaving the
store unmoved, not merely told no — can still sign out, and then a contributor's
identical write is accepted. Role gating's own tests inject a principal onto the scope
and never touch the login handler, so nothing else proves the role that handler stamps
into a cookie is the role the gate later reads back out.

Not a redundant integration test: ``test_secure`` only ever holds cookies it minted
itself, ``test_auth_sessions`` runs the login page with no gate in front of it, and
``test_auth_revocation`` never speaks HTTP. Every step below crosses a boundary those
three each stand on only one side of. Each assertion names its step, so a future
breakage reads as "step 5: the cookie no longer admits", not ``assert 401 == 200``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from driftless.api import secure
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.api.secure import TokenGate
from driftless.auth import sessions
from driftless.auth.passwords import hash_password
from driftless.models import Business, User
from driftless.web import csrf

GATED = "/"  # any path the gate does not open; the home page, as test_secure gates it
LISTED = "/projects"  # a gated JSON read, so the walk covers both surfaces a viewer uses
WRITTEN = "/businesses"  # the write, chosen because its body needs nothing but a name
TOKEN = "deployment-bearer-token"  # pragma: allowlist secret  (in-test gate token)
SECRET = "test-signing-secret"  # pragma: allowlist secret  (throwaway in-test signing key)
PASSWORD = "correct horse battery"  # pragma: allowlist secret  (throwaway in-test password)
_TOKEN_FIELD = re.compile(r'name="csrf_token" value="([^"]+)"')


def _deployment(db: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A gated deployment as the container serves one: real app, real gate, real users.

    ``https``, because both cookies are ``Secure`` by default and an http jar would
    silently drop them — so the flag keeps its production value instead of being
    turned off for the test. The gate sits OUTSIDE FastAPI and so is unreachable by
    ``dependency_overrides``: it takes the test's session directly, while the routes
    inside still need the override. No clock is injected on purpose — the cookie's
    expiry is stamped by the app's own login router from the wall clock, and both
    halves of the walk must read the same one; expiry against a pinned clock is
    ``test_secure``'s and ``test_auth_sessions``' job.

    Shared by the two fixtures below, which differ only in who is on the staff: one
    deployment wired twice would drift, and the walks would stop being comparable.
    """
    monkeypatch.setenv(sessions.SECRET_ENV, SECRET)
    monkeypatch.delenv(sessions.SECURE_ENV, raising=False)  # Secure cookies, as in production
    real_app.dependency_overrides[get_session] = lambda: db
    gated = TokenGate(real_app, TOKEN, session_scope=lambda: nullcontext(db))
    with TestClient(gated, base_url="https://testserver", follow_redirects=False) as client:
        yield client
    real_app.dependency_overrides.clear()


def _staff(db: Session, **roles: str) -> None:
    """Seed one real login per ``username=role``, digest and all — no injected principals."""
    for username, role in roles.items():
        db.add(User(username=username, password_hash=hash_password(PASSWORD), role=role))
    db.commit()


@pytest.fixture
def browser(db: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The deployment above, staffed by one admin — a role that may write anything."""
    _staff(db, jp="admin")
    yield from _deployment(db, monkeypatch)


@pytest.fixture
def staffed_browser(db: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The same deployment staffed by the two roles the write gate splits on, no admin.

    Both walk the *same* client in turn, as one shared workstation would: it is the
    same app object, the same gate and the same store for both, so the only thing that
    differs between the refused write and the accepted one is who signed in.
    """
    _staff(db, vic="viewer", cora="contributor")
    yield from _deployment(db, monkeypatch)


def _sign_in(client: TestClient, username: str) -> int:
    """Sign ``username`` in the way a browser does, and answer the POST's status.

    The first walk deliberately does not call this: it asserts on the login form itself
    — that the gate leaves it reachable, that it renders a CSRF token — which is that
    walk's whole point, so folding those steps in here would delete its assertions.
    """
    form = client.get("/login")
    field = _TOKEN_FIELD.search(form.text)
    assert field is not None, f"the login form rendered no CSRF token for {username}"
    body = {"username": username, "password": PASSWORD, "csrf_token": field.group(1)}
    return client.post("/login", data=body).status_code


def test_the_whole_sign_in_walk_from_the_gate_to_revocation(browser: TestClient) -> None:
    refused = browser.get(GATED)
    assert (refused.status_code, refused.headers.get("location")) == (303, "/login"), (
        f"step 1: {GATED} did not send a signed-out browser to the sign-in form "
        f"({refused.status_code}) — a page address is where a person's bookmark points"
    )

    form = browser.get("/login")
    assert form.status_code == 200, (
        f"step 2: the login form is gated ({form.status_code}), so no cookie can ever be "
        "obtained and a gated deployment cannot be signed into — the #1610 defect"
    )

    field = _TOKEN_FIELD.search(form.text)
    assert field is not None, "step 3: the login form rendered no CSRF token to post back"
    body = {"username": "jp", "password": PASSWORD, "csrf_token": field.group(1)}
    posted = browser.post("/login", data=body)
    assert posted.status_code == 303, (
        f"step 3: the right password on a live user was refused ({posted.status_code})"
    )

    captured = browser.cookies.get(sessions.COOKIE)
    assert captured is not None, "step 4: signing in issued no session cookie"

    assert "authorization" not in browser.headers  # the cookie alone, the way a browser has it
    admitted = browser.get(GATED)
    assert admitted.status_code == 200, (
        f"step 5: the session cookie no longer admits to {GATED} ({admitted.status_code}) — a "
        "signed-in browser carries no bearer header, so this is the web UI locked out"
    )

    pair = {"csrf_token": browser.cookies.get(csrf.COOKIE, "")}  # the nav form's own
    out = browser.post("/logout", data=pair)
    assert out.status_code == 303, f"step 6: signing out did not redirect ({out.status_code})"

    browser.cookies.set(sessions.COOKIE, captured)  # what a stolen cookie would replay
    replayed = browser.get(GATED)
    assert replayed.status_code == 401, (
        f"step 7: the captured cookie still admits after sign-out ({replayed.status_code}) — "
        "the epoch, logout's bump of it and the gate's resolve are not composing into revocation"
    )


def _businesses(db: Session) -> int:
    """Rows in the store — the number a refused write must leave exactly where it was."""
    return db.scalar(select(func.count()).select_from(Business)) or 0


def test_a_signed_in_viewer_reads_everything_and_writes_nothing(
    staffed_browser: TestClient, db: Session
) -> None:
    """The role half of the same seam: a real viewer, signed in for real, then refused.

    ``test_secure`` asserts the refusal with a principal it injects onto the scope, and
    the walk above signs in as an admin, who may write. Neither drives a *viewer*
    through the login handler and into the gate, so nothing yet proves the role the
    handler stamps into the cookie is the role the gate reads back out — two features
    that each look right alone, exactly the shape of the #1610 defect.

    Step 4 is the load-bearing one, and it is not the 403: it is the row count either
    side of the refusal. Gating at the chokepoint means the refusal lands *before* the
    route runs, so a viewer's write must be unobservable in the store rather than
    merely reported as failed. Step 6 is the control — the same request, the same
    client, the same body, accepted for a contributor — without which step 4 would
    equally pass if the write were broken for everybody.
    """
    assert _sign_in(staffed_browser, "vic") == 303, "step 1: a viewer cannot sign in at all"
    assert staffed_browser.cookies.get(sessions.COOKIE) is not None, (
        "step 1: the viewer's sign-in issued no session cookie"
    )

    page = staffed_browser.get(GATED)
    assert page.status_code == 200, (
        f"step 2: a viewer is refused the {GATED} page ({page.status_code}) — read access is "
        "the whole point of the role, so this is a viewer with no reason to have an account"
    )

    listed = staffed_browser.get(LISTED)
    assert listed.status_code == 200, f"step 3: a viewer is refused {LISTED} ({listed.status_code})"

    before = _businesses(db)
    refused = staffed_browser.post(WRITTEN, json={"name": "Sneaky"})
    assert refused.status_code == 403, (
        f"step 4: a viewer's POST {WRITTEN} was not refused ({refused.status_code})"
    )
    assert refused.content == secure._WRITE_DENIED, (
        f"step 4: the refusal body is not the gate's own ({refused.content!r})"
    )
    assert _businesses(db) == before, (
        "step 4: the refused write reached the store anyway — the gate answered 403 after the "
        "route had already inserted, so gating at the chokepoint is not happening before it"
    )

    pair = {"csrf_token": staffed_browser.cookies.get(csrf.COOKIE, "")}  # the nav form's own
    out = staffed_browser.post("/logout", data=pair)
    assert out.status_code == 303, (
        f"step 5: a viewer cannot sign out ({out.status_code}) — read-only must never mean "
        "trapped in a session, and /logout is open precisely so the role check cannot reach it"
    )

    assert _sign_in(staffed_browser, "cora") == 303, "step 6: the contributor cannot sign in"
    created = staffed_browser.post(WRITTEN, json={"name": "Legit"})
    assert created.status_code == 201, (
        f"step 6: the contributor's POST {WRITTEN} was refused too ({created.status_code}) — so "
        "step 4 proves nothing about the role; the write is simply broken for everyone"
    )
    assert _businesses(db) == before + 1, "step 6: the accepted write created no row"
