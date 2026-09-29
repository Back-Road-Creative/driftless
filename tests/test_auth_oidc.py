"""Contract for ``/auth/oidc/{start,callback}`` against a stub IdP — no network.

No ``authlib``: the flow is standard library (``urllib``, ``hashlib``, ``secrets``),
with the HTTP fetcher injected so these tests never touch a socket. The ID token is
validated by claim (``iss``, ``aud``, ``exp``, ``nonce``) without a signature check —
sound only because it arrives directly from the token endpoint over TLS, per OIDC
Core 3.1.3.7 item 6 — so every refusal here is a claim mismatch, not a signature one.
Mapping is closed-world: a ``sub`` unbound to any ``User.oidc_subject`` is refused,
never auto-provisioned, and an inactive user is refused identically.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import urllib.request
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.deps import get_session
from driftless.auth import oidc, sessions
from driftless.models import User

ISSUER = "http://127.0.0.1:9999"  # loopback: the https requirement is waived for it
CLIENT_ID = "driftless-test"
CLIENT_SECRET = "shh-its-a-secret"  # pragma: allowlist secret  (throwaway in-test value)
REDIRECT_URI = "https://app.example/auth/oidc/callback"
SESSION_SECRET = "test-signing-secret"  # pragma: allowlist secret  (throwaway in-test value)
NOW = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)


def _b64(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _id_token(payload: dict[str, Any]) -> str:
    header = _b64({"alg": "none"})
    return f"{header}.{_b64(payload)}.sig"


def _discovery(_url: str) -> bytes:
    return json.dumps(
        {"authorization_endpoint": ISSUER + "/authorize", "token_endpoint": ISSUER + "/token"}
    ).encode()


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(oidc.ISSUER_ENV, ISSUER)
    monkeypatch.setenv(oidc.CLIENT_ID_ENV, CLIENT_ID)
    monkeypatch.setenv(oidc.CLIENT_SECRET_ENV, CLIENT_SECRET)
    monkeypatch.setenv(oidc.REDIRECT_URI_ENV, REDIRECT_URI)
    monkeypatch.setenv(sessions.SECRET_ENV, SESSION_SECRET)
    monkeypatch.setenv(sessions.SECURE_ENV, "0")  # TestClient speaks http, not https


@pytest.fixture
def stub(configured: None, db: Session) -> Iterator[tuple[TestClient, dict[str, Any]]]:
    holder: dict[str, Any] = {}

    def token_response(_url: str, _data: dict[str, str]) -> bytes:
        return json.dumps({"id_token": _id_token(holder["payload"])}).encode()

    app = FastAPI()
    app.include_router(
        oidc.create_oidc_router(
            http_get=_discovery, http_post_form=token_response, clock=lambda: NOW
        )
    )
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app, follow_redirects=False) as client:
        yield client, holder


def _start(client: TestClient) -> tuple[str, str]:
    resp = client.get("/auth/oidc/start")
    assert resp.status_code == 303
    query = parse_qs(urlsplit(resp.headers["location"]).query)
    return query["state"][0], query["nonce"][0]


def test_unconfigured_404(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(sessions.SECRET_ENV, SESSION_SECRET)
    app = FastAPI()
    app.include_router(oidc.create_oidc_router())
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app) as client:
        assert client.get("/auth/oidc/start").status_code == 404
        assert client.get("/auth/oidc/callback").status_code == 404


def test_happy_path_lands_on_root(stub: tuple[TestClient, dict[str, Any]], db: Session) -> None:
    client, holder = stub
    db.add(User(username="jp", password_hash="x", role="admin", oidc_subject="alice-sub"))
    db.commit()
    state, nonce = _start(client)
    holder["payload"] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "nonce": nonce,
        "sub": "alice-sub",
    }
    resp = client.get("/auth/oidc/callback", params={"code": "abc123", "state": state})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert sessions.COOKIE in resp.cookies


def test_bad_state_refused(stub: tuple[TestClient, dict[str, Any]]) -> None:
    client, _holder = stub
    _start(client)
    resp = client.get("/auth/oidc/callback", params={"code": "abc123", "state": "not-the-state"})
    assert resp.status_code == 400


def test_nonce_mismatch_refused(stub: tuple[TestClient, dict[str, Any]]) -> None:
    client, holder = stub
    state, _nonce = _start(client)
    holder["payload"] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "nonce": "some-other-nonce",
        "sub": "alice-sub",
    }
    resp = client.get("/auth/oidc/callback", params={"code": "abc123", "state": state})
    assert resp.status_code == 401


def test_wrong_aud_refused(stub: tuple[TestClient, dict[str, Any]]) -> None:
    client, holder = stub
    state, nonce = _start(client)
    holder["payload"] = {
        "iss": ISSUER,
        "aud": "someone-elses-client",
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "nonce": nonce,
        "sub": "alice-sub",
    }
    resp = client.get("/auth/oidc/callback", params={"code": "abc123", "state": state})
    assert resp.status_code == 401


def test_expired_id_token_refused(stub: tuple[TestClient, dict[str, Any]]) -> None:
    client, holder = stub
    state, nonce = _start(client)
    holder["payload"] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "exp": int((NOW - timedelta(minutes=5)).timestamp()),
        "nonce": nonce,
        "sub": "alice-sub",
    }
    resp = client.get("/auth/oidc/callback", params={"code": "abc123", "state": state})
    assert resp.status_code == 401


def test_unknown_sub_refused(stub: tuple[TestClient, dict[str, Any]]) -> None:
    client, holder = stub
    state, nonce = _start(client)
    holder["payload"] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "nonce": nonce,
        "sub": "nobody-binds-this-sub",
    }
    resp = client.get("/auth/oidc/callback", params={"code": "abc123", "state": state})
    assert resp.status_code == 403


def test_inactive_user_refused(stub: tuple[TestClient, dict[str, Any]], db: Session) -> None:
    client, holder = stub
    db.add(
        User(
            username="gone",
            password_hash="x",
            role="viewer",
            is_active=False,
            oidc_subject="alice-sub",
        )
    )
    db.commit()
    state, nonce = _start(client)
    holder["payload"] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "nonce": nonce,
        "sub": "alice-sub",
    }
    resp = client.get("/auth/oidc/callback", params={"code": "abc123", "state": state})
    assert resp.status_code == 403


def test_install_oidc_adds_routes_directly_not_via_include_router(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``install_oidc`` must register with ``add_api_route`` — like
    ``driftless.web.method_map_json.install_method_map_json`` — so neither route
    is swept up as a "page" by the a11y/CSRF/responsive walks, which only expand
    routes an ``include_router`` call contributed."""
    monkeypatch.setenv(sessions.SECRET_ENV, SESSION_SECRET)
    app = FastAPI()
    oidc.install_oidc(app, http_get=_discovery, clock=lambda: NOW)
    app.dependency_overrides[get_session] = lambda: db
    for route in app.routes:
        assert not hasattr(route, "routes"), "install_oidc must not include_router"
    with TestClient(app) as client:
        # Unconfigured: 404, same contract as the include_router-based router.
        assert client.get("/auth/oidc/start").status_code == 404


# --- edges the flow above never reaches: config, helpers and the 5xx refusals ---


def test_config_reads_secret_from_file_and_refuses_plain_http(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    secret_file = tmp_path / "client-secret"
    secret_file.write_text(CLIENT_SECRET + "\n")
    monkeypatch.setenv(oidc.ISSUER_ENV, "https://idp.example")
    monkeypatch.setenv(oidc.CLIENT_ID_ENV, CLIENT_ID)
    monkeypatch.delenv(oidc.CLIENT_SECRET_ENV, raising=False)
    monkeypatch.setenv(oidc.CLIENT_SECRET_FILE_ENV, str(secret_file))
    monkeypatch.setenv(oidc.REDIRECT_URI_ENV, REDIRECT_URI)
    cfg = oidc.config()
    assert cfg is not None and cfg.client_secret == CLIENT_SECRET
    # A cleartext issuer off loopback is "not set up": no flow starts.
    monkeypatch.setenv(oidc.ISSUER_ENV, "http://idp.example")
    assert oidc.config() is None


def test_default_fetchers_use_urllib(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class _Resp:
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def read(self) -> bytes:
            return b"{}"

    def fake_urlopen(req: Any, timeout: float) -> _Resp:
        seen["req"], seen["timeout"] = req, timeout
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert oidc._default_get("https://idp.example/x") == b"{}"
    assert seen["req"] == "https://idp.example/x" and seen["timeout"] == 5
    assert oidc._default_post_form("https://idp.example/token", {"a": "b c"}) == b"{}"
    assert seen["req"].method == "POST" and seen["req"].data == b"a=b+c"


def test_unsign_refuses_every_malformed_shape() -> None:
    key = "k"
    good = oidc._sign({"exp": int((NOW + timedelta(minutes=1)).timestamp())}, key)
    assert oidc._unsign(good, key, NOW) is not None
    assert oidc._unsign("no-dot-no-sig", key, NOW) is None
    body, _, _sig = good.partition(".")
    assert oidc._unsign(body + ".wrongsig", key, NOW) is None
    # Well-signed but not JSON, and well-signed JSON that is not an object.
    for raw in (b"not json", b"[1, 2]"):
        b = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        mac = hmac.new(key.encode(), b.encode(), hashlib.sha256).digest()
        sig = base64.urlsafe_b64encode(mac).decode().rstrip("=")
        assert oidc._unsign(f"{b}.{sig}", key, NOW) is None


def test_decode_id_token_refuses_wrong_part_count_and_bad_json() -> None:
    assert oidc._decode_id_token("only.two") is None
    bad = base64.urlsafe_b64encode(b"not json").decode().rstrip("=")
    assert oidc._decode_id_token(f"h.{bad}.s") is None
    assert oidc._decode_id_token("h." + _b64({"sub": "x"}) + ".s") == {"sub": "x"}


def test_validated_sub_refuses_wrong_issuer() -> None:
    cfg = oidc.OidcConfig(
        issuer=ISSUER, client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI
    )
    payload = {
        "iss": "https://someone-else",
        "aud": CLIENT_ID,
        "exp": 1e12,
        "nonce": "n",
        "sub": "s",
    }
    assert oidc._validated_sub(payload, cfg, "n", NOW) is None


def test_no_session_secret_is_503_on_both_routes(
    configured: None, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(sessions.SECRET_ENV, raising=False)
    app = FastAPI()
    app.include_router(oidc.create_oidc_router(http_get=_discovery, clock=lambda: NOW))
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app, follow_redirects=False) as client:
        assert client.get("/auth/oidc/start").status_code == 503
        assert client.get("/auth/oidc/callback").status_code == 503


def test_discovery_without_endpoints_is_502(configured: None, db: Session) -> None:
    """A discovery document missing either endpoint refuses upstream-style (502)."""
    doc: dict[str, str] = {"authorization_endpoint": ISSUER + "/authorize"}

    def discovery(_url: str) -> bytes:
        return json.dumps(doc).encode()

    app = FastAPI()
    app.include_router(oidc.create_oidc_router(http_get=discovery, clock=lambda: NOW))
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app, follow_redirects=False) as client:
        state, _nonce = _start(client)
        # The state cookie is valid, so the callback reaches discovery and finds no token endpoint.
        resp = client.get("/auth/oidc/callback", params={"code": "abc123", "state": state})
        assert resp.status_code == 502
        doc.clear()
        assert client.get("/auth/oidc/start").status_code == 502
