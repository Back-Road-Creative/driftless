"""Signed session cookies on the standard library's ``hmac`` — no new dependency.

``<b64url(payload)>.<b64url(hmac-sha256)>``; :func:`verify` returns ``None``, never
an exception, for a tampered, malformed or expired value. With
``DRIFTLESS_SESSION_SECRET`` unset nothing is issued: the deliberate opposite of
``driftless.api.secure``'s bearer gate, which stays OPEN when its token is unset —
that gate only *withholds* access, while this cookie *grants* identity, and an
unsigned one is a forgeable login. The expiry is threaded in like every as-of
here, never read from a clock inside, which is what makes it testable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger("driftless.auth")
COOKIE = "driftless_session"
SECRET_ENV = "DRIFTLESS_SESSION_SECRET"  # pragma: allowlist secret  (env var name, not a value)
SECURE_ENV = "DRIFTLESS_COOKIE_SECURE"
_warned = False


def secret() -> str | None:  # the signing key, or None — warning once per process
    global _warned
    value = os.environ.get(SECRET_ENV) or None
    if value is None and not _warned:
        _warned = True
        logger.warning("%s is unset — sign-in is disabled, no session can be issued.", SECRET_ENV)
    return value


def cookie_secure() -> bool:  # ``Secure`` unless opted out — ``0`` for plain-HTTP dev
    return os.environ.get(SECURE_ENV, "1").strip().lower() not in {"0", "false", "no", "off"}


def _mac(body: str, key: str) -> str:
    digest = hmac.new(key.encode(), body.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def plain_int(value: object) -> bool:
    # An ``int`` that is not a ``bool``: ``bool`` subclasses ``int``, and ``id == True``
    # would match row 1, so a flag must never pass for an id or a counter.
    return isinstance(value, int) and not isinstance(value, bool)


def issue(
    user_id: int,
    username: str,
    role: str,
    expires_at: datetime,
    key: str,
    epoch: int | None = None,
) -> str:
    payload: dict[str, Any] = {
        "uid": user_id,
        "name": username,
        "role": role,
        "exp": int(expires_at.timestamp()),
    }
    if epoch is not None:  # absent rather than 0 when unstamped: resolve() then fails closed
        payload["epc"] = epoch
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"{body}.{_mac(body, key)}"


def verify(value: str, key: str, now: datetime) -> dict[str, Any] | None:
    # The payload of a cookie ``key`` signed and ``now`` has not outlived, else ``None``.
    body, _, mac = value.partition(".")
    if not mac or not hmac.compare_digest(_mac(body, key), mac):
        return None
    try:  # base64 and JSON both raise subclasses of ValueError
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    if not isinstance(payload, dict) or not plain_int(payload.get("uid")):
        return None  # a string (or a bool) uid would otherwise round-trip as an identity
    exp = payload.get("exp")
    return dict(payload) if isinstance(exp, int | float) and exp > now.timestamp() else None
