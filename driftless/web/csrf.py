"""The CSRF double-submit pair, minted and checked in ONE place.

A form POST is accepted only when the body's token equals the ``driftless_csrf``
cookie's. Script on another origin can force the request but cannot read our cookie,
so it cannot make the halves agree; the compare is constant-time and a missing half
is never a match. :func:`ensure` REUSES the token the browser already holds rather
than reminting, so two open tabs never invalidate each other's forms and a pinned
as-of still renders byte-identically — only ``/login`` mints per render (:func:`remint`),
its form being handed out before any session exists. :func:`require` raises 403 before
the endpoint reads or writes, so a forgery never reaches the store. No router remembers
any of this: every page renders through :mod:`driftless.web.templating`.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import HTTPException, Request, Response

from driftless.auth import sessions

COOKIE = "driftless_csrf"
FIELD = "csrf_token"  # the hidden input's name, and the template context key
TTL = 12 * 60 * 60  # seconds — the session cookie's own lifetime
_FRESH = "driftless_csrf_fresh"  # scope flag: this render mints rather than reuses


def mint() -> str:
    return secrets.token_urlsafe(16)


def ensure(request: Request) -> str:
    """The token this browser already carries, or a fresh one if it carries none."""
    if request.scope.get(_FRESH):
        return mint()
    return request.cookies.get(COOKIE) or mint()


def remint(request: Request) -> None:  # render a FRESH pair, not the browser's — /login only
    request.scope[_FRESH] = True


def attach(response: Response, token: str, ttl: int = TTL) -> None:
    """Set the cookie half (``SameSite=Lax`` and ``path=/`` are Starlette defaults)."""
    response.set_cookie(COOKIE, token, max_age=ttl, httponly=True, secure=sessions.cookie_secure())


def valid(request: Request, submitted: str) -> bool:
    """Whether ``submitted`` matches the cookie — an empty half is never a match."""
    cookie = request.cookies.get(COOKIE, "")
    return bool(cookie and submitted) and hmac.compare_digest(cookie, submitted)


def require(request: Request, submitted: str) -> None:
    """Refuse an unpaired form POST with 403. The detail never reaches the page."""
    if not valid(request, submitted):
        raise HTTPException(403, "The form's CSRF token is missing or stale.")
