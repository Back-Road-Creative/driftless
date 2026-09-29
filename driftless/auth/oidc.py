"""``/auth/oidc/{start,callback}`` — sign in against an external IdP's ``sub``.

No ``authlib``: the whole authorization-code flow (discovery, PKCE, state/nonce,
confidential-client token exchange) runs on the standard library, so this module
adds no runtime dependency and no hashed-lock recompile. The HTTP fetcher is
injected (:func:`create_oidc_router`'s ``http_get``/``http_post_form``), which is
what lets the tests drive a stub IdP with no network at all.

The ID token is validated by claim — ``iss``, ``aud``, ``exp``, ``nonce`` — with
**no signature check**. That is sound, not lazy: OIDC Core 3.1.3.7 item 6 permits
skipping signature validation for an ID token received directly from the token
endpoint over TLS, since TLS server authentication already establishes who
signed the response. Nothing here ever accepts an ID token handed to it any
other way (front-channel, form post, etc.) — only this module's own token
exchange produces one it will decode.

Mapping is closed-world, like ``driftless.auth.cli``'s other writes: a ``sub``
with no matching ``User.oidc_subject`` is refused outright, never
auto-provisioned — roles and accounts stay a local decision, bound by an admin
through ``driftless user oidc-subject``. An inactive user is refused
identically. On success this issues the *same* session cookie
``driftless.web.login`` issues, through the same :mod:`driftless.auth.sessions`
helpers, so everything downstream (the request gate, logout, revocation) is one
code path regardless of which door a session walked in through.

Unconfigured is the default: with any of the four env vars unset, or an issuer
that is neither ``https://`` nor loopback, both routes answer 404 — there is
nothing to start or complete.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select

from driftless.api.deps import Db
from driftless.auth import sessions
from driftless.models import User
from driftless.web.errors import PageRoute

ISSUER_ENV = "DRIFTLESS_OIDC_ISSUER"
CLIENT_ID_ENV = "DRIFTLESS_OIDC_CLIENT_ID"
CLIENT_SECRET_ENV = "DRIFTLESS_OIDC_CLIENT_SECRET"  # pragma: allowlist secret  (env var name)
#: A path to a file holding the secret, for a deployment that mounts it rather than
#: setting it inline — read once per request, never logged either way.
CLIENT_SECRET_FILE_ENV = "DRIFTLESS_OIDC_CLIENT_SECRET_FILE"  # pragma: allowlist secret
REDIRECT_URI_ENV = "DRIFTLESS_OIDC_REDIRECT_URI"

#: Carries the pending exchange (state, nonce, PKCE verifier) between ``start`` and
#: ``callback`` — signed with the same session secret, short-lived, cleared on use.
STATE_COOKIE = "driftless_oidc_state"
STATE_TTL = timedelta(minutes=10)
#: Matches ``driftless.web.login.SESSION_TTL`` — both doors issue the same lifetime
#: cookie. Not imported from there to avoid a page-module importing a page module;
#: :mod:`driftless.auth.sessions` (which both build on) has no opinion on TTL.
SESSION_TTL = timedelta(hours=12)

HttpGet = Callable[[str], bytes]
HttpPostForm = Callable[[str, dict[str, str]], bytes]


@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str


def _loopback(issuer: str) -> bool:
    return (urllib.parse.urlsplit(issuer).hostname or "") in {"localhost", "127.0.0.1", "::1"}


def config() -> OidcConfig | None:
    """The four settings from the environment, or ``None`` if OIDC is not set up.

    An issuer that is neither ``https://`` nor loopback is treated as not set up
    either — refusing plainly (404) rather than starting a flow that would send a
    client secret in the clear.
    """
    issuer = os.environ.get(ISSUER_ENV)
    client_id = os.environ.get(CLIENT_ID_ENV)
    redirect_uri = os.environ.get(REDIRECT_URI_ENV)
    secret = os.environ.get(CLIENT_SECRET_ENV)
    secret_file = os.environ.get(CLIENT_SECRET_FILE_ENV)
    if not secret and secret_file:
        secret = Path(secret_file).read_text().strip()
    if not issuer or not client_id or not redirect_uri or not secret:
        return None
    if not issuer.startswith("https://") and not _loopback(issuer):
        return None
    return OidcConfig(
        issuer=issuer, client_id=client_id, client_secret=secret, redirect_uri=redirect_uri
    )


def _default_get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 -- fixed, configured issuer
        return bytes(resp.read())


def _default_post_form(url: str, data: dict[str, str]) -> bytes:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")  # noqa: S310 -- configured endpoint
    with urllib.request.urlopen(req, timeout=5) as resp:
        return bytes(resp.read())


def _discover(issuer: str, get: HttpGet) -> dict[str, Any]:
    doc = json.loads(get(issuer.rstrip("/") + "/.well-known/openid-configuration"))
    return doc if isinstance(doc, dict) else {}


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def _sign(payload: dict[str, Any], key: str) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    mac = hmac.new(key.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{base64.urlsafe_b64encode(mac).decode().rstrip('=')}"


def _unsign(value: str, key: str, now: datetime) -> dict[str, Any] | None:
    body, _, sig = value.partition(".")
    if not sig:
        return None
    mac = hmac.new(key.encode(), body.encode(), hashlib.sha256).digest()
    expected = base64.urlsafe_b64encode(mac).decode().rstrip("=")
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    return payload if isinstance(exp, int | float) and exp > now.timestamp() else None


def _decode_id_token(id_token: str) -> dict[str, Any] | None:
    # No signature check here by design — see the module docstring for why that is
    # sound for a token that arrived directly from the token endpoint over TLS.
    parts = id_token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _validated_sub(
    payload: dict[str, Any], cfg: OidcConfig, nonce: str, now: datetime
) -> str | None:
    if payload.get("iss") != cfg.issuer:
        return None
    aud = payload.get("aud")
    auds = aud if isinstance(aud, list) else [aud]
    if cfg.client_id not in auds:
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int | float) or exp <= now.timestamp():
        return None
    if payload.get("nonce") != nonce:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) and sub else None


def create_oidc_router(
    http_get: HttpGet = _default_get,
    http_post_form: HttpPostForm = _default_post_form,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ttl: timedelta = SESSION_TTL,
) -> APIRouter:
    router = APIRouter(route_class=PageRoute)
    max_age = int(ttl.total_seconds())

    @router.get("/auth/oidc/start")
    def start(request: Request) -> Response:
        cfg = config()
        if cfg is None:
            raise HTTPException(status_code=404)
        key = sessions.secret()
        if key is None:
            raise HTTPException(
                status_code=503, detail=f"Sign-in is unavailable: {sessions.SECRET_ENV} is unset."
            )
        doc = _discover(cfg.issuer, http_get)
        auth_endpoint = doc.get("authorization_endpoint")
        if not isinstance(auth_endpoint, str):
            raise HTTPException(
                status_code=502, detail="OIDC discovery did not name an authorization endpoint."
            )
        now = clock()
        state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        verifier, challenge = _pkce_pair()
        cookie_value = _sign(
            {
                "state": state,
                "nonce": nonce,
                "verifier": verifier,
                "exp": int((now + STATE_TTL).timestamp()),
            },
            key,
        )
        params = {
            "response_type": "code",
            "client_id": cfg.client_id,
            "redirect_uri": cfg.redirect_uri,
            "scope": "openid",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        response = RedirectResponse(
            f"{auth_endpoint}?{urllib.parse.urlencode(params)}", status_code=303
        )
        response.set_cookie(
            STATE_COOKIE,
            cookie_value,
            max_age=int(STATE_TTL.total_seconds()),
            httponly=True,
            secure=sessions.cookie_secure(),
        )
        return response

    @router.get("/auth/oidc/callback")
    def callback(request: Request, db: Db) -> Response:
        cfg = config()
        if cfg is None:
            raise HTTPException(status_code=404)
        key = sessions.secret()
        if key is None:
            raise HTTPException(
                status_code=503, detail=f"Sign-in is unavailable: {sessions.SECRET_ENV} is unset."
            )
        now = clock()
        raw_cookie = request.cookies.get(STATE_COOKIE)
        pending = _unsign(raw_cookie, key, now) if raw_cookie else None
        code, got_state = request.query_params.get("code"), request.query_params.get("state")
        if pending is None or not code or got_state != pending.get("state"):
            raise HTTPException(
                status_code=400, detail="This sign-in attempt has expired — please try again."
            )
        doc = _discover(cfg.issuer, http_get)
        token_endpoint = doc.get("token_endpoint")
        if not isinstance(token_endpoint, str):
            raise HTTPException(
                status_code=502, detail="OIDC discovery did not name a token endpoint."
            )
        token_response = json.loads(
            http_post_form(
                token_endpoint,
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": cfg.redirect_uri,
                    "client_id": cfg.client_id,
                    "client_secret": cfg.client_secret,
                    "code_verifier": pending["verifier"],
                },
            )
        )
        id_token = token_response.get("id_token") if isinstance(token_response, dict) else None
        payload = _decode_id_token(id_token) if isinstance(id_token, str) else None
        sub = _validated_sub(payload, cfg, pending["nonce"], now) if payload is not None else None
        if sub is None:
            raise HTTPException(status_code=401, detail="Sign-in could not be completed.")
        user = db.scalars(select(User).where(User.oidc_subject == sub)).one_or_none()
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=403, detail="No local account is bound to this identity."
            )
        landing = RedirectResponse("/", status_code=303)
        value = sessions.issue(
            user.id, user.username, user.role, now + ttl, key, user.session_epoch
        )
        landing.set_cookie(
            sessions.COOKIE, value, max_age=max_age, httponly=True, secure=sessions.cookie_secure()
        )
        landing.delete_cookie(STATE_COOKIE)
        return landing

    return router


def install_oidc(
    app: FastAPI,
    http_get: HttpGet = _default_get,
    http_post_form: HttpPostForm = _default_post_form,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ttl: timedelta = SESSION_TTL,
) -> None:
    """Add ``/auth/oidc/start`` and ``/auth/oidc/callback`` straight to ``app`` --
    ``add_api_route``, not ``include_router`` -- the same reason and the same
    pattern as :func:`driftless.web.method_map_json.install_method_map_json`:
    neither route ever renders an HTML page (only a redirect or an
    :class:`~fastapi.HTTPException`), so the "every page the app registers"
    sweeps -- ``tests/test_web_a11y.py``, ``tests/test_web_csrf.py``,
    ``tests/test_web_responsive.py`` and friends, all of which walk only the
    routes an ``include_router`` call contributed -- must never see them.
    ``create_oidc_router`` itself stays unchanged so an isolated test app can
    still ``include_router`` it directly.
    """
    router = create_oidc_router(http_get, http_post_form, clock, ttl)
    for route in router.routes:
        app.add_api_route(
            route.path,  # type: ignore[attr-defined]
            route.endpoint,  # type: ignore[attr-defined]
            methods=sorted(route.methods or ()),  # type: ignore[attr-defined]
        )
