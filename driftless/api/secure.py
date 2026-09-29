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
surface itself, because a cookie has to be obtainable before it can be presented.
Constructed directly with no token, :class:`TokenGate` itself stays open — that is
how the suite builds one — but :func:`create_secured_app`, what the container
actually runs, now REFUSES TO START on that same absence unless
``DRIFTLESS_ALLOW_UNAUTHENTICATED=1`` opts in for local development, in which case
it warns once so open is loud, not silent, either way.

Which of the three authenticated the request is stamped on the scope beside the
principal, because CSRF turns on exactly that: a cookie is ambient — a browser attaches
it to whatever another origin causes — and a header never is, so a form POST authenticated
by a bearer needs no double-submit pair (:func:`driftless.web.credentials.require_pair_unless_bearer`).

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

The two kinds default in opposite directions on purpose, at the class itself: no
token → open, because that half only *withholds* access, where no
``DRIFTLESS_SESSION_SECRET`` → no cookie can ever authorize, because that half
*grants* an identity and an unsigned cookie is a forgeable one (see
:mod:`driftless.auth.sessions`). ``create_secured_app`` tightens the token half
further still — a deployment forgetting the token is a worse failure than a
deployment forgetting the secret is loud about, so it refuses to start rather than
silently opening (see :func:`create_secured_app`).

Wrapping the app rather than editing it keeps this file disjoint from the API
code (it only imports the finished app), and the same ``app`` object serves both
the open and the gated mode. Binding to ``127.0.0.1`` is the compose's job, not
this file's.
"""

from __future__ import annotations

import hmac
import json
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
from driftless.api.versioning import API_PREFIX

# The gate's own store lookup comes from the db layer's own lazy factory: whichever
# of the gate and the first route arrives first builds the single factory (and
# registers the changelog listener) and the other borrows it. Two engines against
# one SQLite file is a real bug. It is ``session_scope`` and not the ``get_session``
# dependency because that one now credits its writes to the request's signed-in
# user, which needs a ``Request`` this middleware does not have — and the gate's
# lookup is a read that credits nobody.
from driftless.db.session import session_scope
from driftless.auth import principal, sessions, tokens
from driftless.web import credentials
from driftless.web.errors import PageRoute, admin_only_page, read_only_page

logger = logging.getLogger("driftless.secure")
SessionScope = Callable[[], AbstractContextManager[Session]]

TOKEN_ENV = "DRIFTLESS_API_TOKEN"
LEGACY_TOKEN_ENV = "PMHUB_API_TOKEN"  # pre-rename name, honoured for one cycle
# The startup refusal's one override, in the idiom of ``DRIFTLESS_ALLOW_SCHEMA_AHEAD``
# (:mod:`driftless.api.app`): a name that says exactly what it grants, checked for the
# exact string "1" so a leftover non-empty value left by some other tool cannot opt in
# by accident. See :func:`create_secured_app`.
ALLOW_UNAUTHENTICATED_ENV = "DRIFTLESS_ALLOW_UNAUTHENTICATED"
# Run with NO shared bearer at all: every request must carry a per-user credential, so
# every write lands with an actor. Checked for the exact string "1", like its siblings.
#
# This is how the permanent shared bootstrap credential is *retired* rather than made
# attributable. Teaching ``DRIFTLESS_API_TOKEN`` to resolve a principal was the other
# option and is worse: it reverses the recorded decision that the bootstrap credential
# is un-role-gated, and it would silently put a name on the one honest on-behalf-of
# write the service has (see :func:`driftless.api.deps.signer`). Not using the shared
# credential reverses nothing — it just stops being in the picture.
REQUIRE_USER_AUTH_ENV = "DRIFTLESS_REQUIRE_USER_AUTH"
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
# Role gating's FLOOR splits on the METHOD, not on the route: everyone signed in
# reads, only ``_WRITE_ROLES`` write at all. Doing the floor here rather than per
# route is what makes it robust by construction — a write route added later is
# gated whether or not anyone remembers to ask. Anything outside this set counts as
# a write, so an unlisted method fails closed. ``_PRIVILEGED_PATHS`` below adds a
# second, narrower tier on top of this floor for the one write that needs it — it
# can only ever raise the bar an unclassified route already clears, never lower it,
# so the robustness argument above still holds for every route this file has not named.
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# ``viewer`` — the column default — is the one role left out of ordinary writes
# (the roles themselves: ``driftless/models/auth.py``).
_WRITE_ROLES = frozenset({"admin", "contributor"})
# SUPERSEDES the earlier decision that there was deliberately no admin-only tier
# (docs/decisions-superseded.md, "Administration boundary"): a sign-off is a
# governance act, not an edit — it can permanently suppress or restore a live
# threat, and the ledger it appends to is by design never patched or deleted
# (see :func:`driftless.services.sign_offs.create_sign_off`). Two addresses reach
# that ONE write: ``POST /sign-offs`` calls ``create_sign_off``, and the browser
# form at ``POST /sign-off`` calls the same service rather than its own row
# (:func:`driftless.web.sign_off.sign_off`) — both are named here, or the page form
# would quietly reopen the hole gating only the JSON route would leave. Derived
# and compared as an exact set against the live route table in
# ``tests/test_secure.py``, so neither a stale entry here nor a third route
# reaching the same write can drift from this list unnoticed.
#
# The versioned twin of the JSON route is the THIRD address, and it is built from
# ``API_PREFIX`` rather than typed out: this check matches a path literally, so a
# versioned route the list does not name reaches ``create_sign_off`` without the
# admin floor. That is a privilege hole, not a routing detail, and it is exactly
# what the exact-set test above caught when ``/api/v1`` was introduced. Any future
# prefix must be composed here the same way. (The page form is NOT versioned —
# HTML pages take no prefix, so there is no twin of ``/sign-off`` to name.)
_PRIVILEGED_PATHS = frozenset({"/sign-offs", "/sign-off", API_PREFIX + "/sign-offs"})
_WRITE_DENIED = b'{"detail":"writes need the contributor or admin role"}'
_PRIVILEGED_DENIED = b'{"detail":"this action needs the admin role"}'
_UNAUTHENTICATED = b'{"detail":"missing or invalid bearer token"}'
# The two reasons a request never reaches ``self._inner`` -- see :func:`_log_refusal`.
# ``_REASON_UNAUTHENTICATED`` covers both true anonymity and a credential that was
# presented but resolved nobody (a wrong bearer, a forged or stale cookie) -- the
# gate cannot and does not distinguish those for the *response* (see
# :meth:`TokenGate._refuse_anonymous`), so the refusal log does not invent a finer
# split either.
_REASON_UNAUTHENTICATED = "unauthenticated"
_REASON_INSUFFICIENT_ROLE = "insufficient_role"


def _log_refusal(scope: Scope, reason: str, *, who: principal.Principal | None = None) -> None:
    """Record a refusal this gate answers itself, on its own ``driftless.secure``
    logger -- the module already has one, for the route-table and dev-mode
    warnings above.

    Nothing else sees this request: the gate sits OUTSIDE the app
    (:func:`create_secured_app`), and a refusal returns without ever calling
    ``self._inner`` -- so the request log (:mod:`driftless.api.logging`) and the
    metrics middleware (:mod:`driftless.api.metrics`), both installed *inside*
    the app this gate wraps, never run for it. Without this line a burst of
    rejected credentials -- credential stuffing, a misconfigured client looping
    on 401, a revoked token still in use -- is indistinguishable in every other
    signal this service emits from no traffic at all.

    INFO, deliberately, not the WARNING this module already uses for genuine
    misconfiguration (an unreadable route table, a deployment running open): a
    refusal is ordinary, expected traffic under normal operation -- a scanner
    probing the API, a stale client, a viewer clicking a write button their role
    does not grant -- and :mod:`driftless.api.logging` sets the same precedent,
    logging every request, failed or not, at INFO. Raising this to WARNING would
    make routine 401/403 traffic indistinguishable, in an operator's filters,
    from the conditions this module already reserves that level for.

    **Never the credential.** Not the presented token, not any part or hash of
    it, not the ``Authorization`` or ``Cookie`` header -- :mod:`driftless.api.logging`
    states the rule this line has to honour just as strictly: a credential in a
    log line is a leak, and a log is copied to places the database is not. There
    is deliberately nothing here to redact, because nothing about the
    credential is ever read for this purpose in the first place.

    ``who`` -- the resolved principal -- is included only for a write refusal.
    By the time that branch runs the caller has already authenticated (a cookie
    or a per-user token resolved *someone*; only their role was insufficient),
    so naming them is not a credential disclosure -- it is the fact an operator
    most needs to act on a repeated 403: whose account keeps asking for access
    it does not have. A 401 resolves no principal at all, so there is no name
    to log there, only the request's own shape.

    No ``request_id``: :mod:`driftless.api.logging` mints and stamps that id
    from *inside* the app this gate wraps, so a refused request -- which never
    reaches ``self._inner`` -- is never assigned one. Inventing an id here would
    be a second, disconnected generator with nothing on the other end to
    correlate against, which is worse than the line simply not carrying one.
    """
    if not logger.isEnabledFor(logging.INFO):
        return
    client = scope.get("client")
    record: dict[str, object] = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "event": "refused",
        "reason": reason,
        "method": scope.get("method", "GET"),
        "path": scope.get("path", ""),
        "client": client[0] if client else None,
    }
    if who is not None:
        record["username"] = who.username
    logger.info(json.dumps(record))


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


def is_open_path(path: str) -> bool:
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
        require_identity: bool = False,
        session_scope: SessionScope = session_scope,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inner = inner
        self._token = token
        # Default ``False`` so ``token=None`` keeps meaning "open", which is what the
        # existing callers and their tests pin. The new mode is opt-in and explicit:
        # no shared bearer AND no anonymous access, so every admitted request has a
        # principal and every write it makes is attributable.
        self._require_identity = require_identity
        self._session_scope = session_scope
        self._pages = _page_patterns(inner)  # read once here, so a test rebuilds by re-wrapping
        self._clock = clock  # cookie expiry is the one clock here, threaded in like every as-of

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._inner(scope, receive, send)  # type: ignore[operator]
            return
        path = scope.get("path", "")
        if is_open_path(path):  # a public asset needs no identity, so none is looked up
            await self._inner(scope, receive, send)  # type: ignore[operator]
            return
        token, (who, kind) = self._token, self._credential(scope)
        if kind is not None:
            # Resolved once per request: role gating, the audit actor and the CSRF rule all
            # read what this stamps, and none of them looks a credential up a second time.
            state = scope.setdefault("state", {})
            state[credentials.CREDENTIAL_KEY], state["principal"] = kind, who
        if who is not None and _refuses_write(scope, who):  # before ``_inner``: no route, no row
            await self._refuse_write(scope, receive, send, who)
            return
        # Open only when there is no shared bearer AND nothing asked for identity. The
        # ``token is not None`` guard preserves the old short-circuit exactly: with a
        # token configured this is the same test as before, and with none configured
        # the old code never reached ``_authorized`` either.
        open_access = token is None and not self._require_identity
        if open_access or who is not None or (token is not None and _authorized(scope, token)):
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
        _log_refusal(scope, _REASON_UNAUTHENTICATED)
        if _anonymous(scope) and self._is_page(scope):
            await RedirectResponse(_LOGIN_PATH, status_code=_SEE_OTHER)(scope, receive, send)
            return
        await _respond(send, 401, _UNAUTHENTICATED)

    def _is_page(self, scope: Scope) -> bool:
        """Whether this request's address is one of the app's own HTML page routes."""
        path = scope.get("path", "")
        return any(pattern.match(path) for pattern in self._pages)

    async def _refuse_write(
        self, scope: Scope, receive: Receive, send: Send, who: principal.Principal
    ) -> None:
        """The 403: the designed page when the request addressed a page, else the JSON body.

        Which SURFACE answers is keyed on the path alone, not on the method — a viewer
        POSTing to a read-only page address is still a reader at a page address, and a
        browser should never be handed a JSON dump. Every other surface, the API
        included, is byte for byte what it was: no page route matches, so nothing changes.

        Which WORDING it carries is keyed on the tier that refused, on both surfaces.
        ``who`` reached ``_WRITE_ROLES`` and was still refused only by way of
        :data:`_PRIVILEGED_PATHS` — that is the one branch in :func:`_refuses_write`
        that can turn a writer away — so the role IS the reason, read back rather than
        re-derived from the path, which would be a second copy free to drift from the
        first. It matters because the two readers need opposite instructions: a viewer
        is told to ask for contributor access, and telling a contributor the same would
        send them to ask for the role they already hold.
        """
        _log_refusal(scope, _REASON_INSUFFICIENT_ROLE, who=who)
        admin_only = who.role in _WRITE_ROLES
        if self._is_page(scope):
            page = admin_only_page if admin_only else read_only_page
            await page(Request(scope))(scope, receive, send)
            return
        await _respond(send, 403, _PRIVILEGED_DENIED if admin_only else _WRITE_DENIED)

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
        (:func:`driftless.web.credentials.require_pair_unless_bearer`). DECIDED: the shared
        ``DRIFTLESS_API_TOKEN`` resolves nobody but is stamped all the same — it is a
        header a caller attached deliberately, which is the whole of that argument, and
        it stays the un-role-gated bootstrap credential it already was.
        """
        who = self._from_cookie(scope)
        if who is not None:
            return who, credentials.COOKIE_CREDENTIAL
        who = self._from_token(scope)
        if who is not None:
            return who, credentials.TOKEN_CREDENTIAL
        if self._token is not None and _authorized(scope, self._token):
            return None, credentials.SHARED_CREDENTIAL
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
            return tokens.resolve(db, presented, self._clock())


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
    """Whether ``who``'s role forbids this request.

    Only reached once a principal resolved, so a request carrying nothing but the
    shared bearer token is NOT role gated — DECIDED: ``DRIFTLESS_API_TOKEN`` is the
    bootstrap/admin credential and keeps full write access. A signed-in viewer is
    gated even with no token configured, because the identity is what is being
    checked, not the token.

    Two tiers, both fail closed on the SAME floor: any write method outside
    ``_READ_METHODS`` needs at least ``_WRITE_ROLES`` — an unrecognised path gets
    exactly that floor and nothing weaker, whether or not this file ever names it.
    A path in ``_PRIVILEGED_PATHS`` narrows the floor further, to ``admin`` alone.
    """
    if scope.get("method", "GET") in _READ_METHODS:
        return False
    if who.role not in _WRITE_ROLES:
        return True
    return scope.get("path", "") in _PRIVILEGED_PATHS and who.role != "admin"


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
    """Wrap the API in the token gate, reading the token from the environment.

    A missing token used to serve the whole API open with only a warning in a log
    nobody reads — a forgotten secret silently widening access, the fail-open
    configuration bug. It now REFUSES to start unless ``ALLOW_UNAUTHENTICATED_ENV``
    opts in explicitly: a process that will not start is loud, an open API is not.

    Three configurations, and only three:

    * ``REQUIRE_USER_AUTH_ENV=1`` — no shared bearer; every request presents a per-user
      cookie or ``dfl_…`` token, so every write it makes names an actor. This is the
      configuration to deploy: mint a service account with ``driftless user add`` and
      ``driftless token add`` and give it to the client that used to hold the shared one.
    * ``TOKEN_ENV`` set — the shared bootstrap credential, un-role-gated, writes landing
      ``actor=None``. Still supported, still what a fresh install starts on.
    * Neither, plus ``ALLOW_UNAUTHENTICATED_ENV=1`` — open, for local development.

    Setting the first two together is refused rather than resolved. Either the operator
    thinks the shared credential still works (it does not, in this mode) or that this
    mode is on (it would be, silently disabling a configured secret) — and a wrong
    mental model about which credentials authorize is the failure this module exists
    to prevent, so it fails at startup where it is loud.
    """
    token = os.environ.get(TOKEN_ENV) or os.environ.get(LEGACY_TOKEN_ENV) or None
    if os.environ.get(REQUIRE_USER_AUTH_ENV) == "1":
        if token is not None:
            raise RuntimeError(
                f"{REQUIRE_USER_AUTH_ENV}=1 and {TOKEN_ENV} are both set — refusing to "
                f"start. In this mode the shared credential does not authorize anything; "
                f"unset it, or unset {REQUIRE_USER_AUTH_ENV} to keep using it."
            )
        return TokenGate(app, None, require_identity=True)
    if token is None:
        if os.environ.get(ALLOW_UNAUTHENTICATED_ENV) != "1":
            raise RuntimeError(
                f"{TOKEN_ENV} is unset — refusing to start an unauthenticated API. "
                f"Set {TOKEN_ENV} (or the legacy {LEGACY_TOKEN_ENV}), set "
                f"{REQUIRE_USER_AUTH_ENV}=1 to require a per-user credential instead, "
                f"or set {ALLOW_UNAUTHENTICATED_ENV}=1 to run open for local development."
            )
        logger.warning("%s is unset — the API is running open (development mode).", TOKEN_ENV)
    return TokenGate(app, token)


def __getattr__(name: str) -> TokenGate:
    """Build ``secured`` lazily, on first access rather than at import.

    Most of the test suite imports this module only for :class:`TokenGate` and never
    touches ``secured`` at all — building it eagerly here would make every one of
    those imports pay :func:`create_secured_app`'s startup refusal, so the whole
    suite would need the token (or the dev-mode opt-in) just to collect. Only an
    actual resolution of the attribute — uvicorn's ``driftless.api.secure:secured`` —
    pays the check, exactly once, which is also the only place the refusal is meant
    to fire.
    """
    if name == "secured":
        return create_secured_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
