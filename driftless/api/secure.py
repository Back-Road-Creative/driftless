"""Deployment hardening: a credential-gated ASGI wrapper around the API.

The container runs ``uvicorn driftless.api.secure:secured``. One gate, three
credential kinds: a request is let through by a bearer token matching the shared
``DRIFTLESS_API_TOKEN`` (or the pre-rename ``PMHUB_API_TOKEN``, honoured for one
deprecation cycle), by a per-user ``dfl_…`` token minted by ``driftless token add``
(:mod:`driftless.auth.tokens`), **or** by a signed ``driftless_session`` cookie whose
user the store still vouches for — a browser holds a cookie, never a header, so gating
the API without that kind would lock the web UI out. Three deliberate
exceptions: the health probe (``/health``) is passed through uncredentialed so an
orchestrator can check the app without one — it answers whether the store replies
and nothing more, which is what makes it safe to leave open, where ``/health/ready``
names a revision and stays gated — ``/static`` assets are public, and so is the login
surface itself, because a cookie has to be obtainable before it can be presented. With no token configured the gate stays open — local
development — and warns once so a token forgotten in production is loud, not silent.

Which of the three authenticated the request is stamped on the scope beside the
principal, because CSRF turns on exactly that: a cookie is ambient — a browser attaches
it to whatever another origin causes — and a header never is, so a form POST authenticated
by a bearer needs no double-submit pair (:func:`driftless.web.pages._require_pair_unless_bearer`).

A cookie and a per-user token both resolve to one ``Principal`` carrying a *role*,
and this is where it is enforced: a signed-in viewer, and the tokens they hold, may
read every surface and write nothing. The shared token resolves nobody and is
deliberately not role-gated — it is the bootstrap credential. Gating the one chokepoint
instead of each route is the point — a write route added later is gated by
construction. Role is checked strictly after the three exceptions above, so a
viewer can always sign in, sign out and load the CSS. A viewer refused at a *page*
address — a submitted web form — is answered with the designed HTML refusal rather
than the JSON body, decided from the app's own page routes (see :func:`_page_patterns`)
and never from an ``Accept`` header. The same split decides the 401: a request that
presented no credential at all, at a page address, is redirected to the sign-in form
(:meth:`TokenGate._refuse_anonymous`); every other refusal keeps the JSON body a
script already parses, byte for byte.

The two kinds default in opposite directions on purpose. No token → open, because
that half only *withholds* access. No ``DRIFTLESS_SESSION_SECRET`` → no cookie can
ever authorize, because that half *grants* an identity and an unsigned cookie is
a forgeable one (see :mod:`driftless.auth.sessions`).

Wrapping the app rather than editing it keeps this file disjoint from the API
code (it only imports the finished app), and the same ``app`` object serves both
the open and the gated mode. Binding to ``127.0.0.1`` is the compose's job, not
this file's.
"""

from __future__ import annotations

import hmac
import logging
import os
import re
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import BaseRoute
from starlette.types import Message, Receive, Scope, Send

from driftless.api.app import app

# The gate's own store lookup comes from the API's *own* lazy factory: whichever of
# the gate and the first route arrives first builds the single factory (and registers
# the changelog listener) and the other borrows it. Two engines against one SQLite
# file is a real bug. It is ``session_scope`` and not the ``get_session`` dependency
# because that one now credits its writes to the request's signed-in user, which needs
# a ``Request`` this middleware does not have — and the gate's lookup is a read that
# credits nobody.
from driftless.api.app import session_scope
from driftless.auth import principal, sessions, tokens
from driftless.web import pages
from driftless.web.errors import PageRoute, read_only_page

logger = logging.getLogger("driftless.secure")
SessionScope = Callable[[], AbstractContextManager[Session]]

TOKEN_ENV = "DRIFTLESS_API_TOKEN"
LEGACY_TOKEN_ENV = "PMHUB_API_TOKEN"  # pre-rename name, honoured for one cycle
_HEALTH_PATH = "/health"
_STATIC_ROOT = "/static"
_BEARER = "Bearer "  # the scheme, matched exactly — see :func:`_bearer`
# The authentication surface itself. A gate that hides the login page cannot be
# signed into: with a token set, a browser would be refused at the form and could
# never obtain the cookie the gate accepts. Which is exactly why login carries a
# CSRF double submit, one constant-time refusal for every failure, and a rate
# limit — the protection is in the handler, not in hiding it. Logout is open so a
# cookie already gone stale can still be cleared; unauthenticated it deletes a
# cookie and redirects, granting nothing.
_LOGIN_PATH = "/login"
_AUTH_PATHS = frozenset({_LOGIN_PATH, "/logout"})
# 303 See Other, the status the login router already redirects with: a browser follows
# it as a GET, so a form POSTed from a page whose session died lands on the form rather
# than replaying itself at it.
_SEE_OTHER = 303
# Role gating splits on the METHOD, not on the route: everyone signed in reads, only
# ``_WRITE_ROLES`` write. Doing it here rather than per route is what makes it robust
# by construction — a write route added later is gated whether or not anyone remembers
# to ask. Anything outside this set counts as a write, so an unlisted method fails closed.
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# ``viewer`` — the column default — is the one role left out. There is deliberately no
# admin-only tier: user management is the ``driftless user`` CLI, and a tier nothing
# needs yet would be a guess (the roles themselves: ``driftless/models/auth.py``).
_WRITE_ROLES = frozenset({"admin", "contributor"})
_WRITE_DENIED = b'{"detail":"writes need the contributor or admin role"}'
_UNAUTHENTICATED = b'{"detail":"missing or invalid bearer token"}'


def _leaves(route: BaseRoute) -> list[BaseRoute]:
    """``route`` itself, or the routes an ``include_router`` call nested under it.

    FastAPI hangs an included router's routes off a wrapper rather than copying them
    onto the app, and depending on the version the children sit on ``routes`` or on
    ``original_router.routes`` — so a naive walk of ``app.routes`` finds no page at
    all. Same shape as ``tests/test_web_routes_not_shadowed.py``, which walks the app
    for the same reason. A ``Mount`` exposes neither and counts as a leaf.
    """
    for holder in (route, getattr(route, "original_router", None)):
        children = getattr(holder, "routes", None)
        if children:
            return [leaf for child in children for leaf in _leaves(child)]
    return [route]


def _page_patterns(inner: object) -> tuple[re.Pattern[str], ...]:
    """The compiled paths of every HTML page route reachable from ``inner``.

    Walked once per gate, never per request. A page router builds its routes with
    ``route_class=PageRoute`` (:mod:`driftless.web.errors`), so this reads the same
    fact ``PAGE_SCOPE_KEY`` records — the surface the request matches — rather than
    an ``Accept`` header a browser and a client can both send. The gate runs before
    routing and cannot read that stamp, but the route table is knowable up front.

    An inner app exposing no routes, or a table this cannot read, yields no patterns
    and every refusal stays JSON: a gate that raises is worse than a gate that does
    not know the surface.
    """
    try:
        routes: Iterable[BaseRoute] = getattr(inner, "routes", ()) or ()
        return tuple(
            leaf.path_regex
            for route in routes
            for leaf in _leaves(route)
            if isinstance(leaf, PageRoute)
        )
    except Exception:  # a shape this walk does not know is not worth a 500
        logger.warning("the route table could not be read: refusals will answer JSON.")
        return ()


def _is_open_path(path: str) -> bool:
    """Whether ``path`` is public — the health probe, a static asset, or sign-in.

    ``/static`` and ``/static/…`` are open; ``/static-export`` or a future
    ``/statistics`` route is not, so a prefix match cannot accidentally leave a
    gated route ungated. The health and auth paths are matched exactly, for the
    same reason: a future ``/login-admin`` must not inherit the allowance, and
    ``/health/ready`` must not — it discloses the store's revision, which is the
    whole reason it lives inside the gate (:func:`driftless.api.app.health_ready`).
    """
    return (
        path == _HEALTH_PATH
        or path in _AUTH_PATHS
        or path == _STATIC_ROOT
        or path.startswith(_STATIC_ROOT + "/")
    )


def _cookie(scope: Scope, name: str) -> str | None:
    """Cookie ``name`` read off the raw ASGI headers, or ``None``.

    Hand-parsed because middleware has no Starlette ``Request``: a missing,
    duplicated or malformed ``Cookie`` header yields ``None``, never an exception.
    """
    for key, value in scope["headers"]:
        if key != b"cookie":
            continue
        header: str = value.decode("latin-1")  # raw ASGI headers are untyped bytes pairs
        for part in header.split(";"):
            label, sep, raw = part.partition("=")
            if sep and label.strip() == name:
                return raw.strip()
    return None


def _bearer(scope: Scope) -> str | None:
    """The value of this request's ``Authorization: Bearer …`` header, or ``None``.

    Hand-parsed off the raw ASGI headers for the same reason :func:`_cookie` is:
    middleware has no Starlette ``Request``. The scheme is matched exactly, as
    :func:`_authorized`'s whole-header compare already does — a stricter parser is
    the fail-closed one — and a missing or malformed header yields ``None``.
    """
    for key, value in scope["headers"]:
        header: str = value.decode("latin-1")  # raw ASGI headers are untyped bytes pairs
        if key == b"authorization" and header.startswith(_BEARER):
            return header[len(_BEARER) :]
    return None


class TokenGate:
    """ASGI middleware requiring a bearer token or a session cookie, except on open paths.

    A resolved identity — from either a cookie or a per-user token — is then held to
    its role: writes need contributor or admin.
    """

    def __init__(
        self,
        inner: object,
        token: str | None,
        *,
        session_scope: SessionScope = session_scope,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inner = inner
        self._token = token
        self._session_scope = session_scope
        self._pages = _page_patterns(inner)  # read once here, so a test rebuilds by re-wrapping
        self._clock = clock  # cookie expiry is the one clock here, threaded in like every as-of

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._inner(scope, receive, send)  # type: ignore[operator]
            return
        path = scope.get("path", "")
        if _is_open_path(path):  # a public asset needs no identity, so none is looked up
            await self._inner(scope, receive, send)  # type: ignore[operator]
            return
        token, (who, kind) = self._token, self._credential(scope)
        if kind is not None:
            # Resolved once per request: role gating, the audit actor and the CSRF rule all
            # read what this stamps, and none of them looks a credential up a second time.
            state = scope.setdefault("state", {})
            state[pages.CREDENTIAL_KEY], state["principal"] = kind, who
        if who is not None and _refuses_write(scope, who):  # before ``_inner``: no route, no row
            await self._refuse_write(scope, receive, send)
            return
        if token is None or who is not None or _authorized(scope, token):
            await self._inner(scope, receive, send)  # type: ignore[operator]
            return
        await self._refuse_anonymous(scope, receive, send)

    async def _refuse_anonymous(self, scope: Scope, receive: Receive, send: Send) -> None:
        """The 401: the sign-in form when a browser asked for a page with nothing to
        present, else the JSON body every client already parses, byte for byte.

        The target is the constant ``_LOGIN_PATH`` and nothing else. **Do not add a
        ``?next=``.** A return path taken from the request is an open redirect until it
        is validated, and validating one properly — scheme, host, and every spelling of
        ``//`` — is far more surface than saving a reader one click. ``/login`` is itself
        an open path, so the landing can never be refused in a loop.

        DECIDED: only a request that presented NOTHING is redirected. A wrong bearer, a
        forged cookie, and a live cookie whose epoch the store has moved past all keep
        the JSON 401. The gate cannot tell those apart without plumbing a reason out of
        :func:`principal.resolve`, and the strict reading of that set is the right one:
        ``driftless user disable`` is what bumps an epoch, and sending a disabled account
        to a form that will refuse it is the loop the rule exists to prevent. Ordinary
        expiry still reaches the form — the cookie's ``max-age`` is the session TTL, so a
        browser drops it before the signature goes stale and presents nothing next time.
        """
        if _anonymous(scope) and self._is_page(scope):
            await RedirectResponse(_LOGIN_PATH, status_code=_SEE_OTHER)(scope, receive, send)
            return
        await _respond(send, 401, _UNAUTHENTICATED)

    def _is_page(self, scope: Scope) -> bool:
        """Whether this request's address is one of the app's own HTML page routes."""
        path = scope.get("path", "")
        return any(pattern.match(path) for pattern in self._pages)

    async def _refuse_write(self, scope: Scope, receive: Receive, send: Send) -> None:
        """The 403: the designed page when the request addressed a page, else the JSON body.

        Keyed on the path alone, not on the method — a viewer POSTing to a read-only
        page address is still a reader at a page address, and a browser should never
        be handed a JSON dump. Every other surface, the API included, is byte for byte
        what it was: no page route matches, so nothing changes.
        """
        if self._is_page(scope):
            await read_only_page(Request(scope))(scope, receive, send)
            return
        await _respond(send, 403, _WRITE_DENIED)

    def _credential(self, scope: Scope) -> tuple[principal.Principal | None, str | None]:
        """The identity behind this request's credential, and WHICH kind carried it.

        DECIDED: a request carrying both a cookie and a bearer is answered as its
        cookie. A browser sends its cookie automatically, so preferring it means
        attaching a header can never *drop* an identity — every request that carries
        a cookie behaves exactly as it did before tokens were accepted, and this unit
        can only add admissions.

        The kind rides along because CSRF turns on it and nothing else can tell: only an
        *ambient* credential can be forged cross-site, so a cookie request presents the
        double-submit pair and a bearer one has nothing to prove
        (:func:`driftless.web.pages._require_pair_unless_bearer`). DECIDED: the shared
        ``DRIFTLESS_API_TOKEN`` resolves nobody but is stamped all the same — it is a
        header a caller attached deliberately, which is the whole of that argument, and
        it stays the un-role-gated bootstrap credential it already was.
        """
        who = self._from_cookie(scope)
        if who is not None:
            return who, pages.COOKIE_CREDENTIAL
        who = self._from_token(scope)
        if who is not None:
            return who, pages.TOKEN_CREDENTIAL
        if self._token is not None and _authorized(scope, self._token):
            return None, pages.SHARED_CREDENTIAL
        return None, None

    def _from_cookie(self, scope: Scope) -> principal.Principal | None:
        """The identity behind this request's session cookie, or ``None`` for none.

        No cookie means no database work at all, and no signing secret means no
        cookie authorizes — an unsigned one could be minted by anybody.
        """
        value = _cookie(scope, sessions.COOKIE)
        if value is None:
            return None
        key = sessions.secret()
        if key is None:
            return None
        payload = sessions.verify(value, key, self._clock())
        if payload is None:
            return None
        with self._session_scope() as db:
            return principal.resolve(db, payload)

    def _from_token(self, scope: Scope) -> principal.Principal | None:
        """The live identity behind a presented ``dfl_…`` token, or ``None`` for none.

        Two things are settled before the store is opened, so a request the gate can
        answer from the header alone costs no query: the shared ``DRIFTLESS_API_TOKEN``,
        which is the bootstrap credential and NOT a per-user token (resolving it would
        also role-gate the one credential decided to keep full write access), and any
        value carrying no mint prefix. Everything past that is :func:`tokens.resolve`'s
        job — revoked, deactivated owner, unknown digest all come back ``None`` there
        rather than being checked a second time here.
        """
        presented = _bearer(scope)
        if presented is None:
            return None
        if self._token is not None and hmac.compare_digest(presented, self._token):
            return None  # the bootstrap credential: no query, and no role gate either
        if not presented.startswith(tokens.PREFIX):
            return None  # not one of ours — ``resolve`` agrees, without a session opened
        with self._session_scope() as db:
            return tokens.resolve(db, presented)


def _anonymous(scope: Scope) -> bool:
    """Whether the request offered no credential of any kind.

    Deliberately broader than the two parsers above: ANY ``Authorization`` header counts
    as presented, including one :func:`_bearer` refuses to read, and any
    ``driftless_session`` cookie counts, including a forged or a revoked one. The
    redirect answers "you presented nothing"; "what you presented is no good" is a 401,
    so an unreadable credential fails closed to the JSON body rather than to the form.
    """
    if _cookie(scope, sessions.COOKIE) is not None:
        return False
    return not any(name == b"authorization" for name, _ in scope["headers"])


def _refuses_write(scope: Scope, who: principal.Principal) -> bool:
    """Whether ``who``'s role forbids this request's method.

    Only reached once a principal resolved, so a request carrying nothing but the
    shared bearer token is NOT role gated — DECIDED: ``DRIFTLESS_API_TOKEN`` is the
    bootstrap/admin credential and keeps full write access. A signed-in viewer is
    gated even with no token configured, because the identity is what is being
    checked, not the token.
    """
    return scope.get("method", "GET") not in _READ_METHODS and who.role not in _WRITE_ROLES


def _authorized(scope: Scope, token: str) -> bool:
    """Whether the request carries ``Authorization: Bearer <token>``.

    Uses a constant-time compare so the token cannot be recovered by timing the
    response to guesses.
    """
    expected = f"Bearer {token}".encode()
    return any(
        name == b"authorization" and hmac.compare_digest(value, expected)
        for name, value in scope["headers"]
    )


async def _respond(send: Send, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    message: Message = {"type": "http.response.body", "body": body}
    await send(message)


def create_secured_app() -> TokenGate:
    """Wrap the API in the token gate, reading the token from the environment."""
    token = os.environ.get(TOKEN_ENV) or os.environ.get(LEGACY_TOKEN_ENV) or None
    if token is None:
        logger.warning("%s is unset — the API is running open (development mode).", TOKEN_ENV)
    return TokenGate(app, token)


secured = create_secured_app()
