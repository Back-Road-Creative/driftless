"""The login page — ``GET``/``POST /login`` and ``POST /logout``.

Signing in is all this surface does: **no route is protected here.** A session
only changes what the nav offers; the request gate and roles are the next PR.
Both refusals ("no such user", "wrong password") render one message with one
status, a missing user is verified against a dummy digest so absence cannot be
timed either, and an inactive user is refused identically. The CSRF double submit
lives in :mod:`driftless.web.csrf`, shared with the other form POSTs; login alone
mints a FRESH token per render rather than reusing the browser's, because its
form is handed out before any session exists.

The cookie is stamped with the user's ``session_epoch`` so the store can revoke
it (:mod:`driftless.auth.principal`), and ``POST /logout`` *increments* that
epoch: signing out kills every cookie that login ever issued to the user, not
just this browser's — so that bump needs the CSRF pair every page now renders
(:mod:`driftless.web.templating`). Repeated failures are throttled by
:class:`_Attempts`, against the same injected ``clock`` the expiry is stamped from —
per (username, resolved client), plus a per-client cap across all usernames that
refuses a flood before it can buy a scrypt.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.deps import get_session
from driftless.auth import sessions
from driftless.auth.passwords import hash_password, verify_password
from driftless.models import User
from driftless.web import csrf
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

Db = Annotated[Session, Depends(get_session)]
FormStr = Annotated[str, Form()]

SESSION_TTL = timedelta(hours=12)
LOGIN_WINDOW = timedelta(minutes=15)  # how long failures are remembered for
LOGIN_MAX_ATTEMPTS = 5  # failures per (username, client) inside one window
LOGIN_CLIENT_MAX = 30  # failures per client across ALL usernames inside one window
_MAX_TRACKED = 4096  # keys the attempt store will hold — see :class:`_Attempts`
# One wording, one status for every refusal: which half was wrong is what an attacker asks.
_REFUSED = "Username or password is incorrect."
# A throttled attempt says so plainly (429) instead of hiding behind ``_REFUSED``: the
# key is (username, client), and the counter rises for usernames that do not exist too,
# so this answer tells its reader only what they already did — never whether a login
# exists. Being honest is what lets a locked-out colleague know to wait rather than
# keep guessing a password that was right all along.
_THROTTLED = f"Too many sign-in attempts — wait {LOGIN_WINDOW.seconds // 60} minutes, then retry."
# The digest of a random string nobody holds: verifying a username that does not
# exist against it costs the same scrypt as a real one, so absence is not timeable.
_DUMMY_DIGEST = hash_password(secrets.token_urlsafe(32))


class _Attempts:
    """Failed sign-ins per (username, client), in this process, bounded two ways.

    Keyed on **both** halves: per-username alone would let one attacker lock every
    colleague out, per-client alone would let a botnet grind one login down. ``now``
    is passed in from the router's ``clock`` and never read here, so the window is
    testable like every other as-of. Store size is bounded by evicting the least
    recently touched key while its window has expired, then by a hard
    ``_MAX_TRACKED`` ceiling — so a caller cycling usernames cannot grow it even
    inside one window. Losing a counter to that ceiling only costs one attacker a
    few extra guesses; unbounded memory would cost the service.
    """

    def __init__(self) -> None:
        self._seen: dict[tuple[str, str], tuple[int, datetime]] = {}

    def __len__(self) -> int:
        return len(self._seen)

    def blocked(self, key: tuple[str, str], now: datetime, limit: int = LOGIN_MAX_ATTEMPTS) -> bool:
        count, first = self._seen.get(key, (0, now))
        return count >= limit and now - first < LOGIN_WINDOW

    def fail(self, key: tuple[str, str], now: datetime) -> None:
        self._evict(now)
        count, first = self._seen.pop(key, (0, now))
        if now - first >= LOGIN_WINDOW:  # the old window closed: this failure starts a new one
            count, first = 0, now
        self._seen[key] = (count + 1, first)  # re-inserted last, so dict order is recency

    def clear(self, key: tuple[str, str]) -> None:
        self._seen.pop(key, None)  # a correct password ends the streak

    def _evict(self, now: datetime) -> None:
        while self._seen:  # the front is the least recently touched key
            key, (_, first) = next(iter(self._seen.items()))
            if now - first < LOGIN_WINDOW:
                break
            del self._seen[key]
        while len(self._seen) >= _MAX_TRACKED:
            del self._seen[next(iter(self._seen))]


def create_login_router(
    clock: Callable[[], datetime] = lambda: datetime.now(UTC), ttl: timedelta = SESSION_TTL
) -> APIRouter:  # sessions are stamped from ``clock`` and expire after ``ttl``
    router = APIRouter(route_class=PageRoute)  # a refused sign-out renders the page shell
    max_age = int(ttl.total_seconds())
    attempts = _Attempts()  # one store per router, so a test owns its own
    # A second store, keyed on the client alone: cycling usernames dodges ``attempts``
    # forever, and every dodge used to buy a full scrypt against the dummy digest
    # (~16.7 MiB and tens of ms) — so this cap refuses the flood before the verify.
    # Never cleared on success, or interleaving one valid credential would launder it.
    floods = _Attempts()

    def _form(request: Request, error: str | None, status: int, username: str = "") -> HTMLResponse:
        csrf.remint(request)  # a fresh pair per render, never the browser's
        # Every refusal keeps the username the user just typed (escaped data, never
        # markup) and refocuses the field; ``StrictUndefined`` makes omitting it a crash.
        # ``field_errors`` is always empty here: every refusal below ("wrong password",
        # "no such user", throttled, expired form) is deliberately form-level, never
        # naming a field — pinning the blame to username or password would tell an
        # attacker which half was right. It rides the context so login.html can share
        # the SAME summary macro wizard.html uses, rather than its own copy that would
        # drift the moment one of the two changed.
        page: dict[str, Any] = {"error": error, "username": username, "field_errors": {}}
        return TEMPLATES.TemplateResponse(request, "login.html", page, status_code=status)

    @router.get("/login", response_class=HTMLResponse)
    def login_form(request: Request) -> HTMLResponse:
        return _form(request, None, 200)

    @router.post("/login")
    def login_submit(
        request: Request, db: Db, username: FormStr, password: FormStr, csrf_token: FormStr = ""
    ) -> Response:
        if not csrf.valid(request, csrf_token):
            return _form(request, "That form expired — please try again.", 400, username)
        key = sessions.secret()
        if key is None:  # an unsigned cookie is forgeable: issue nothing
            unavailable = f"Sign-in is unavailable: {sessions.SECRET_ENV} is unset."
            return _form(request, unavailable, 503, username)
        now, tally = clock(), _key(request, username)
        source = _key(request, "")  # its own store, so "" cannot collide with a username
        if attempts.blocked(tally, now) or floods.blocked(source, now, LOGIN_CLIENT_MAX):
            return _form(request, _THROTTLED, 429, username)  # before the read and the scrypt
        user = db.scalars(select(User).where(User.username == username)).one_or_none()
        # The verify runs on every attempt, real user or not: same cost, same reading.
        stored = user.password_hash if user is not None else _DUMMY_DIGEST
        if not verify_password(password, stored) or user is None or not user.is_active:
            attempts.fail(tally, now)  # counted for absent users too, else 429 is an oracle
            floods.fail(source, now)
            return _form(request, _REFUSED, 401, username)
        attempts.clear(tally)
        landing = RedirectResponse("/", status_code=303)
        epoch = user.session_epoch  # the copy the store compares against on every request
        value = sessions.issue(user.id, user.username, user.role, now + ttl, key, epoch)
        _set(landing, sessions.COOKIE, value, max_age)
        landing.delete_cookie(csrf.COOKIE)
        return landing

    @router.post("/logout")
    def logout(request: Request, db: Db, csrf_token: FormStr = "") -> RedirectResponse:
        """Clearing this browser needs nothing; revoking every device needs the pair —
        so a client never handed one still gets its own cookie dropped, while a body
        that does not match the cookie half is refused before :func:`_revoke`."""
        paired = csrf.valid(request, csrf_token)
        if csrf.COOKIE in request.cookies and not paired:
            csrf.require(request, csrf_token)
        landing = RedirectResponse("/login", status_code=303)
        landing.delete_cookie(sessions.COOKIE)
        cookie, key = request.cookies.get(sessions.COOKIE), sessions.secret()
        payload = sessions.verify(cookie, key, clock()) if cookie and key else None
        if payload is not None and paired:  # absent, forged or expired: clear and redirect
            _revoke(db, payload)
        return landing

    return router


def _key(request: Request, username: str) -> tuple[str, str]:
    # The client half is ``request.client`` — the peer uvicorn has RESOLVED (under
    # ``--proxy-headers`` that is the X-Forwarded-For caller, never the proxy). No raw
    # header is read here, so a spoofed header can never choose its own bucket.
    return (username, request.client.host if request.client is not None else "")


def _revoke(db: Session, payload: dict[str, Any]) -> None:
    """Bump the signer-out's ``session_epoch`` — the same revocation ``user disable`` does.

    Signing out here ends the session on *every* device, because the epoch is what
    every cookie is checked against and there is no per-cookie record to expire — which
    is why the caller only gets here on a valid CSRF pair.
    """
    user = db.scalars(select(User).where(User.id == payload["uid"])).one_or_none()
    if user is None:
        return
    user.session_epoch += 1  # audited through the ChangeLog like any other write
    db.commit()


def _set(page: Response, name: str, value: str, ttl: int) -> None:
    # The flags in one place (``SameSite=Lax`` and ``path=/`` are Starlette defaults).
    page.set_cookie(name, value, max_age=ttl, httponly=True, secure=sessions.cookie_secure())
