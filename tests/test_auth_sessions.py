"""Contract for signed-cookie sessions and the login page.

Pinned: the cookie is unforgeable and expires against a threaded-in clock; every
refusal (bad CSRF, wrong password, unknown user, disabled user, no secret) reads
alike and issues nothing; no existing route became protected. Also pinned: a
minted cookie carries the user's ``session_epoch`` so the store resolves it,
logout bumps that epoch and so revokes every device, and repeated failures are
throttled per username *and* client against the same threaded-in clock — the client
being the peer uvicorn resolved, with a per-client cap across usernames refused
before the scrypt ever runs.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.types import Receive, Scope, Send

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.auth import principal, sessions
from driftless.auth.passwords import hash_password
from driftless.models import User
from driftless.web import csrf, login

NOW = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)
# pragma: allowlist secret  (fixture literals for a throwaway in-test user)
SECRET, PASSWORD = "test-signing-secret", "correct horse battery"  # pragma: allowlist secret
_TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')
_ECHO = re.compile(r'value="[^"]*"')  # scrubs every echoed value, the CSRF pair included


@pytest.fixture
def client(db: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # The app the server actually runs, with one active and one disabled user.
    monkeypatch.setenv(sessions.SECRET_ENV, SECRET)
    monkeypatch.setenv(sessions.SECURE_ENV, "0")  # TestClient speaks http, not https
    digest = hash_password(PASSWORD)
    db.add(User(username="jp", password_hash=digest, role="admin"))
    db.add(User(username="gone", password_hash=digest, is_active=False))
    db.commit()
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app) as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


@pytest.fixture
def paced(client: TestClient, db: Session) -> Iterator[tuple[TestClient, list[datetime]]]:
    """A second client on a router of its own: a fresh attempt store and a clock we move.

    ``real_app``'s login router is built once per process, so its rate-limit store
    outlives any one test; the limit is only testable on a router this test owns.
    Borrows ``client`` for the seeded users and the signing env.
    """
    now = [NOW]
    own = FastAPI()
    own.include_router(login.create_login_router(lambda: now[0]))
    own.dependency_overrides[get_session] = lambda: db
    with TestClient(own) as paced_client:
        yield paced_client, now


def _user(db: Session, username: str) -> User:
    return db.scalars(select(User).where(User.username == username)).one()


def _submit(client: TestClient, user: str, password: str, csrf: str = "") -> httpx.Response:
    # Load the form (minting the CSRF pair), then post it back.
    match = _TOKEN.search(client.get("/login").text)
    assert match is not None
    body = {"username": user, "password": password, "csrf_token": csrf or match.group(1)}
    return client.post("/login", data=body, follow_redirects=False)


def test_a_signed_cookie_round_trips_and_nothing_else_verifies() -> None:
    value = sessions.issue(7, "jp", "admin", LATER, SECRET)
    assert (sessions.verify(value, SECRET, NOW) or {})["name"] == "jp"
    body, mac = value.split(".")
    forged = sessions.issue(7, "root", "admin", LATER, SECRET).split(".")[0]
    for bad in (
        f"{forged}.{mac}",  # tampered payload
        f"{body}.{'A' * len(mac)}",  # tampered signature
        sessions.issue(7, "jp", "admin", LATER, "another secret"),  # signed elsewhere
        "not.a.cookie",
    ):
        assert sessions.verify(bad, SECRET, NOW) is None, bad
    assert sessions.verify(value, SECRET, LATER + timedelta(seconds=1)) is None  # expired


def test_the_epoch_is_stamped_only_when_passed_and_a_user_id_must_be_a_plain_integer() -> None:
    unstamped = sessions.verify(sessions.issue(7, "jp", "admin", LATER, SECRET), SECRET, NOW) or {}
    assert "epc" not in unstamped  # today's callers are unchanged; resolve() fails closed on this
    stamped = sessions.issue(7, "jp", "admin", LATER, SECRET, 3)
    assert (sessions.verify(stamped, SECRET, NOW) or {})["epc"] == 3
    for bad_uid in ("7", True, None):  # a string id used to round-trip; ``bool`` subclasses ``int``
        signed = sessions.issue(bad_uid, "jp", "admin", LATER, SECRET)  # type: ignore[arg-type]
        assert sessions.verify(signed, SECRET, NOW) is None, bad_uid


def test_every_refusal_reads_alike_and_none_of_them_issues_a_cookie(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # wrong password, no such user, and a real password on a disabled user
    attempts = (("jp", "wrong"), ("nobody", PASSWORD), ("gone", PASSWORD))
    refused = [_submit(client, user, password) for user, password in attempts]
    assert {r.status_code for r in refused} == {401}
    # Only the fresh pair and the caller's own echoed username differ — the echo mirrors
    # what THEY typed, so it can never say which half was wrong or whether a login exists.
    assert len({_ECHO.sub("", r.text) for r in refused}) == 1
    assert all(sessions.COOKIE not in r.cookies for r in refused)
    assert _submit(client, "jp", PASSWORD, csrf="not-the-minted-token").status_code == 400

    monkeypatch.delenv(sessions.SECRET_ENV, raising=False)  # unsigned would be forgeable
    monkeypatch.setattr(sessions, "_warned", False)
    with caplog.at_level(logging.WARNING, logger="driftless.auth"):
        unsigned = _submit(client, "jp", PASSWORD)
    assert unsigned.status_code == 503 and sessions.COOKIE not in unsigned.cookies
    assert sessions.SECRET_ENV in caplog.text


def test_a_correct_password_sets_an_httponly_cookie_and_logout_clears_it(
    client: TestClient,
) -> None:
    response = _submit(client, "jp", PASSWORD)
    assert response.status_code == 303 and response.headers["location"] == "/"
    flags = "".join(response.headers.get_list("set-cookie")).lower()
    assert "httponly" in flags and "samesite=lax" in flags
    assert sessions.verify(client.cookies[sessions.COOKIE], SECRET, datetime.now(UTC)) is not None
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert not client.cookies.get(sessions.COOKIE)


def test_a_minted_cookie_carries_the_users_epoch_so_the_store_resolves_it(
    client: TestClient, db: Session
) -> None:
    _submit(client, "jp", PASSWORD)
    payload = sessions.verify(client.cookies[sessions.COOKIE], SECRET, datetime.now(UTC)) or {}
    jp = _user(db, "jp")
    assert payload["epc"] == jp.session_epoch  # stamped from the row, never assumed
    assert principal.resolve(db, payload) == principal.Principal(jp.id, "jp", "admin")


def _sign_out(client: TestClient) -> httpx.Response:
    # The nav's sign-out form, pair included — loading a page is what hands it over.
    client.get("/")
    token = client.cookies.get(csrf.COOKIE, "")
    return client.post("/logout", data={"csrf_token": token}, follow_redirects=False)


def test_logout_revokes_every_live_cookie_and_still_redirects_without_one(
    client: TestClient, db: Session
) -> None:
    _submit(client, "jp", PASSWORD)
    elsewhere = client.cookies[sessions.COOKIE]  # the same login as another browser holds it
    before = _user(db, "jp").session_epoch
    assert _sign_out(client).status_code == 303
    assert _user(db, "jp").session_epoch == before + 1  # the bump IS the revocation
    stale = sessions.verify(elsewhere, SECRET, datetime.now(UTC)) or {}
    assert stale and principal.resolve(db, stale) is None  # signed, unexpired, and dead anyway

    for junk in (None, "not.a.cookie", sessions.issue(999, "ghost", "admin", LATER, SECRET, 0)):
        if junk is not None:
            client.cookies.set(sessions.COOKIE, junk)
        assert _sign_out(client).status_code == 303
    assert _user(db, "jp").session_epoch == before + 1  # nothing else was revoked


def test_repeated_failures_are_throttled_per_username_and_client(
    paced: tuple[TestClient, list[datetime]],
) -> None:
    limited, now = paced
    checked = [_submit(limited, "jp", "wrong") for _ in range(login.LOGIN_MAX_ATTEMPTS)]
    assert {r.status_code for r in checked} == {401}  # every attempt up to the cap is answered
    refused = _submit(limited, "jp", PASSWORD)  # ...then even the right password waits
    assert refused.status_code == 429 and login._THROTTLED in refused.text
    assert sessions.COOKIE not in refused.cookies
    assert _submit(limited, "gone", PASSWORD).status_code == 401  # another username is not locked
    now[0] = NOW + login.LOGIN_WINDOW  # the window rolled over on the injected clock
    assert _submit(limited, "jp", PASSWORD).status_code == 303


def _peer(app: FastAPI, host: str) -> TestClient:
    """A client whose requests arrive with ``host`` already in ``scope["client"]`` —
    exactly what uvicorn's ``--proxy-headers`` writes there after resolving
    ``X-Forwarded-For`` from a trusted proxy. The app never reads raw headers."""

    async def resolved(scope: Scope, receive: Receive, send: Send) -> None:
        await app(dict(scope, client=(host, 61234)), receive, send)

    return TestClient(resolved)


def test_the_throttle_keys_the_client_uvicorn_resolved_so_peers_never_share_a_bucket(
    client: TestClient, db: Session
) -> None:
    """The key's client half is ``request.client`` — the peer uvicorn has RESOLVED, not
    the proxy's own address. Behind the shipped Caddy proxy every request used to carry
    the proxy's docker IP, so five bad passwords from anyone locked a known username out
    globally; with resolved peers (the deploy half turns them on) each caller gets their
    own bucket, and this is the app half's proof that the two halves compose."""
    own = FastAPI()
    own.include_router(login.create_login_router(lambda: NOW))
    own.dependency_overrides[get_session] = lambda: db
    attacker, colleague = _peer(own, "198.51.100.9"), _peer(own, "203.0.113.7")
    for _ in range(login.LOGIN_MAX_ATTEMPTS):
        assert _submit(attacker, "jp", "wrong").status_code == 401
    assert _submit(attacker, "jp", PASSWORD).status_code == 429  # the attacker is held
    assert _submit(colleague, "jp", PASSWORD).status_code == 303  # the colleague is not


def test_a_refusal_keeps_the_typed_username_and_focuses_it(client: TestClient) -> None:
    """Every refusal used to hand back an empty form: 400/401/429/503 all made the
    user retype the username they just typed. It is kept — as escaped DATA, never
    markup — and focused so a screen reader lands where the retry starts."""
    field = re.compile(r'<input name="username"[^>]*>')
    refused = _submit(client, "jp", "wrong")
    kept = field.search(refused.text)
    assert kept is not None and 'value="jp"' in kept.group(0) and "autofocus" in kept.group(0)
    fresh = field.search(client.get("/login").text)
    assert fresh is not None and 'value=""' in fresh.group(0)  # a first render assumes nothing
    assert "autofocus" not in fresh.group(0)
    hostile = _submit(client, '"><script>alert(1)</script>', "wrong")
    assert '"><script>' not in hostile.text  # Jinja escaping kept it data


def test_a_username_rotating_client_is_refused_before_the_verify(
    paced: tuple[TestClient, list[datetime]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cycling usernames never trips the per-username key, yet every such request used
    to run a full scrypt against the dummy digest (~16.7 MiB and tens of ms) — free
    KDF work for any caller. One client's failures cap across ALL usernames too, and
    the capped request is refused before the verify ever runs."""
    limited, _ = paced
    verifies: list[str] = []
    monkeypatch.setattr(login, "verify_password", lambda pw, stored: bool(verifies.append(pw)))
    churned = [_submit(limited, f"ghost-{n}", "wrong") for n in range(login.LOGIN_CLIENT_MAX)]
    assert {r.status_code for r in churned} == {401}  # every attempt under the cap is answered
    refused = _submit(limited, "ghost-fresh", "wrong")
    assert refused.status_code == 429 and login._THROTTLED in refused.text
    assert len(verifies) == login.LOGIN_CLIENT_MAX  # the capped request never paid the scrypt


def test_the_counter_restarts_once_its_window_rolls_over() -> None:
    """A failure after the window closed opens a NEW window at zero — without the reset
    in ``fail()``, ``first`` never advances, so an attacker who trips lockout once and
    waits it out could keep guessing forever with ``blocked()`` never true again. A
    later-touched live key shields ours from the eviction front: eviction must not be
    what happens to reset the counter, the window check in ``fail()`` must be."""
    attempts, key = login._Attempts(), ("jp", "10.0.0.1")
    for _ in range(login.LOGIN_MAX_ATTEMPTS):
        attempts.fail(key, NOW)
    attempts.fail(("colleague", "10.0.0.2"), NOW + timedelta(minutes=2))  # the shield
    attempts.fail(key, NOW + timedelta(minutes=3))  # re-touched: now behind the shield
    rolled = NOW + login.LOGIN_WINDOW + timedelta(minutes=1)  # ours expired, the shield live
    assert not attempts.blocked(key, rolled)  # the old window closed
    for _ in range(login.LOGIN_MAX_ATTEMPTS - 1):
        attempts.fail(key, rolled)
    assert not attempts.blocked(key, rolled)  # a fresh streak, not the old one + 4
    attempts.fail(key, rolled)
    assert attempts.blocked(key, rolled)  # five NEW failures trip it again


def test_expired_keys_are_evicted_when_the_next_failure_arrives() -> None:
    """The store's first bound: a failure evicts every key whose window has expired,
    so the map holds live windows only — not merely anything under ``_MAX_TRACKED``."""
    attempts = login._Attempts()
    for n in range(3):
        attempts.fail((f"u{n}", "10.0.0.4"), NOW)
    attempts.fail(("fresh", "10.0.0.4"), NOW + login.LOGIN_WINDOW)
    assert len(attempts) == 1  # the three expired keys are gone, not retained


def test_the_attempt_store_windows_per_key_clears_on_success_and_cannot_grow() -> None:
    attempts = login._Attempts()
    key, elsewhere = ("jp", "10.0.0.1"), ("jp", "10.0.0.2")
    for _ in range(login.LOGIN_MAX_ATTEMPTS):
        attempts.fail(key, NOW)
    assert attempts.blocked(key, NOW)
    assert not attempts.blocked(elsewhere, NOW)  # keyed on both halves, so no cross-lockout
    assert not attempts.blocked(key, NOW + login.LOGIN_WINDOW)
    attempts.clear(key)  # a correct password ends the streak
    assert not attempts.blocked(key, NOW)
    for n in range(login._MAX_TRACKED + 20):  # a username-cycling attacker cannot grow it
        attempts.fail((f"u{n}", "10.0.0.3"), NOW)
    assert len(attempts) <= login._MAX_TRACKED


def test_the_nav_offers_sign_in_while_no_existing_route_became_protected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(sessions.SECURE_ENV, raising=False)
    assert sessions.cookie_secure() is True  # Secure is the default; 0 opts out
    assert all(client.get(p).status_code == 200 for p in ("/", "/threats", "/pmbok", "/login"))
    assert 'href="/login"' in client.get("/").text
    client.cookies.set(sessions.COOKIE, "anything")
    assert "/logout" in client.get("/").text
