"""The token gate: health is always open, static is public, everything else needs
a credential when one is configured, and the gate is open when it is not.

Two credential kinds satisfy one gate — a bearer token *or* a signed session
cookie whose user the store still vouches for. The cookie half fails CLOSED with
no signing secret, which is the deliberate opposite of the bearer half failing
open with no token: a gate that withholds access may default to off, an identity
that grants it may not.

The bearer header carries either of two things, and they are not interchangeable:
the shared ``DRIFTLESS_API_TOKEN`` (the bootstrap credential — admitted, deliberately
not role-gated, and costing no query) or a per-user ``dfl_…`` token, which resolves
to the very same :class:`Principal` a cookie yields and is therefore held to its
owner's role and credited on their audit rows, with no second mechanism.

The refusal itself splits by surface, never by ``Accept``: a request that presented
nothing at all, at one of the app's page addresses, is sent to the sign-in form; every
other refusal keeps the JSON body a script already parses, byte for byte.
"""

import ast
import inspect
import logging
import textwrap
from collections.abc import Iterator
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.types import Receive, Scope, Send

from driftless.api import secure
from driftless.api.versioning import API_PREFIX
from driftless.api.app import app, get_session
from driftless.services.sign_offs import create_sign_off
from driftless.auth import sessions, tokens
from driftless.auth.principal import Principal
from driftless.db import Base, new_engine, new_session_factory
from driftless.db import session as db_session
from driftless.db.changelog import ChangeLog, register_changelog
from driftless.models import USER_ROLES, ApiToken, User

TOKEN = "s3cr3t-token"
# One path of each surface, both real routes on the app the server runs: a page form
# a browser can submit, and a JSON CRUD collection a client posts to.
PAGE_WRITE = "/projects/1/status"
API_WRITE = "/projects"
# The two addresses that write the SAME append-only row: both call
# ``driftless.services.sign_offs.create_sign_off`` rather than assembling one.
SIGN_OFF_JSON = "/sign-offs"
SIGN_OFF_PAGE = "/sign-off"
# The versioned twin of the JSON route reaches the SAME write, so it needs the same
# admin floor. It is a third address, not a rename -- see ``_PRIVILEGED_PATHS``.
SIGN_OFF_VERSIONED = f"{API_PREFIX}/sign-offs"
# The gate's unauthenticated body, spelled out here rather than read off the module: a
# refactor that changes what a script parses has to change this literal to stay green.
UNAUTHENTICATED = b'{"detail":"missing or invalid bearer token"}'
NOW = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
EXPIRES = NOW + timedelta(hours=1)
SECRET = "test-signing-secret"  # pragma: allowlist secret  (throwaway in-test signing key)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    # A file, not in-memory: TestClient serves the request on another thread, which
    # would otherwise get its own empty in-memory database.
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        app.dependency_overrides[get_session] = lambda: session
        yield session
        app.dependency_overrides.clear()


def _client(token: str | None) -> TestClient:
    # Never follows: a refusal that redirects is the thing under test, not a step to it.
    return TestClient(secure.TokenGate(app, token), follow_redirects=False)


def test_health_is_always_open(db: Session) -> None:
    for token in (TOKEN, None):
        resp = _client(token).get("/health")
        assert resp.status_code == 200 and resp.json() == {"status": "ok"}


def test_a_protected_path_needs_the_token(db: Session) -> None:
    client = _client(TOKEN)
    assert client.get("/").status_code == 303  # a page, nothing presented: to the form
    assert client.get("/", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = client.get("/", headers={"Authorization": f"Bearer {TOKEN}"})
    assert ok.status_code == 200


def test_the_gate_is_open_when_no_token_is_set(db: Session) -> None:
    assert _client(None).get("/").status_code == 200  # dev mode: no credential needed


def test_static_assets_are_public(db: Session) -> None:
    resp = _client(TOKEN).get("/static/driftless.js")
    assert resp.status_code != 401  # served (or 404), but never gated


def test_a_static_prefix_lookalike_is_still_gated(db: Session) -> None:
    """/static-export must NOT slip through the /static allowance — a real boundary."""
    assert _client(TOKEN).get("/static-export").status_code == 401


def test_create_secured_app_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(secure.TOKEN_ENV, TOKEN)
    gated = secure.create_secured_app()
    assert gated._token == TOKEN


def test_create_secured_app_refuses_to_start_with_no_token_and_no_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defect this unit closes: a token forgotten in production used to serve the
    whole API open with only a warning in a log nobody reads. Now it refuses to start,
    naming the variable to set."""
    monkeypatch.delenv(secure.TOKEN_ENV, raising=False)
    monkeypatch.delenv(secure.LEGACY_TOKEN_ENV, raising=False)
    monkeypatch.delenv(secure.ALLOW_UNAUTHENTICATED_ENV, raising=False)
    with pytest.raises(RuntimeError, match=secure.TOKEN_ENV):
        secure.create_secured_app()


def test_create_secured_app_opts_into_open_mode_explicitly(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Local development keeps a way to run open, but only behind a name that says
    exactly what it does — and the existing warning still fires on that path."""
    monkeypatch.delenv(secure.TOKEN_ENV, raising=False)
    monkeypatch.delenv(secure.LEGACY_TOKEN_ENV, raising=False)
    monkeypatch.setenv(secure.ALLOW_UNAUTHENTICATED_ENV, "1")
    with caplog.at_level(logging.WARNING, logger="driftless.secure"):
        gated = secure.create_secured_app()
    assert gated._token is None
    assert "running open" in caplog.text


@pytest.mark.parametrize("value", ["", "0", "true", "yes", "1 "])
def test_only_the_exact_string_one_opts_into_open_mode(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """The opt-in is compared against ``"1"`` exactly, not coerced to a truthy value, so a
    variable of the same name left set by some other tool — or a shell that appended a
    space — cannot open the API by accident. Anything that is not that one string is a
    refusal, the same as the variable being absent."""
    monkeypatch.delenv(secure.TOKEN_ENV, raising=False)
    monkeypatch.delenv(secure.LEGACY_TOKEN_ENV, raising=False)
    monkeypatch.setenv(secure.ALLOW_UNAUTHENTICATED_ENV, value)
    with pytest.raises(RuntimeError, match=secure.TOKEN_ENV):
        secure.create_secured_app()


def test_secured_is_resolved_lazily_not_at_import_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most of the suite imports this module only for :class:`TokenGate` — if
    ``secured`` were built eagerly at import time, collecting those files would
    already have raised before a single test ran. Only resolving the attribute
    (as uvicorn's ``driftless.api.secure:secured`` does) pays the startup check."""
    monkeypatch.delenv(secure.TOKEN_ENV, raising=False)
    monkeypatch.delenv(secure.LEGACY_TOKEN_ENV, raising=False)
    monkeypatch.delenv(secure.ALLOW_UNAUTHENTICATED_ENV, raising=False)
    with pytest.raises(RuntimeError, match=secure.TOKEN_ENV):
        getattr(secure, "secured")


def test_token_env_names_are_the_renamed_ones() -> None:
    """The exact strings are operational contract — entrypoint.sh and the SOPS
    secrets file export them — so the rename is pinned, not incidental."""
    assert secure.TOKEN_ENV == "DRIFTLESS_API_TOKEN"
    assert secure.LEGACY_TOKEN_ENV == "PMHUB_API_TOKEN"


def test_legacy_token_env_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    """A secrets file still carrying the pre-rename token name keeps gating for
    one deprecation cycle, and the new name wins when both are set."""
    monkeypatch.delenv(secure.TOKEN_ENV, raising=False)
    monkeypatch.setenv(secure.LEGACY_TOKEN_ENV, "legacy-token")
    assert secure.create_secured_app()._token == "legacy-token"
    monkeypatch.setenv(secure.TOKEN_ENV, TOKEN)
    assert secure.create_secured_app()._token == TOKEN


class _Spy:
    """A stand-in inner app that records what the gate left on the ASGI scope."""

    def __init__(self) -> None:
        self.principal: object = None
        self.credential: object = None
        self.calls = 0  # a refusal must never reach here — that is what "before the route" means

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.calls += 1
        self.principal = scope.get("state", {}).get("principal")
        self.credential = scope.get("state", {}).get("credential")
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


@pytest.fixture
def signed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(sessions.SECRET_ENV, SECRET)


def _user(
    db: Session, *, active: bool = True, epoch: int = 0, role: str = "admin", username: str = "jp"
) -> User:
    user = User(
        username=username, password_hash="x", role=role, is_active=active, session_epoch=epoch
    )
    db.add(user)
    db.commit()
    return user


def _gate(db: Session, inner: object = app, token: str | None = TOKEN) -> secure.TokenGate:
    """The gate reading the test's session, on a pinned clock — no wall clock, no engine."""
    return secure.TokenGate(inner, token, session_scope=lambda: nullcontext(db), clock=lambda: NOW)


def _cookie(value: str) -> dict[str, str]:
    # The raw header, because the gate parses ``scope["headers"]`` and not a Request.
    return {"Cookie": f"{sessions.COOKIE}={value}"}


def _issued(user: User, epoch: int | None = 0) -> str:
    return sessions.issue(user.id, user.username, user.role, EXPIRES, SECRET, epoch)


def test_a_session_cookie_authorizes_a_gated_path(db: Session, signed: None) -> None:
    """One gate, two credential kinds: a signed-in browser carries no bearer token."""
    user = _user(db)
    resp = TestClient(_gate(db)).get("/", headers=_cookie(_issued(user)))
    assert resp.status_code == 200


def test_the_resolved_principal_lands_on_the_scope(db: Session, signed: None) -> None:
    """Role gating and per-user audit rows read it next — resolved once, here."""
    spy = _Spy()
    user = _user(db)
    assert TestClient(_gate(db, spy)).get("/", headers=_cookie(_issued(user))).status_code == 204
    assert spy.principal is not None
    assert (spy.principal.uid, spy.principal.role) == (user.id, "admin")  # type: ignore[attr-defined]


def test_an_epochless_cookie_is_refused(db: Session, signed: None) -> None:
    """A cookie minted before epochs existed is one nothing can revoke: fail closed."""
    user = _user(db)
    resp = TestClient(_gate(db)).get("/", headers=_cookie(_issued(user, epoch=None)))
    assert resp.status_code == 401


def test_a_stale_epoch_cookie_is_refused(db: Session, signed: None) -> None:
    user = _user(db)
    value = _issued(user)
    user.session_epoch += 1  # exactly what ``driftless user disable`` does
    db.commit()
    assert TestClient(_gate(db)).get("/", headers=_cookie(value)).status_code == 401


def test_an_inactive_users_cookie_is_refused(db: Session, signed: None) -> None:
    user = _user(db, active=False)
    assert TestClient(_gate(db)).get("/", headers=_cookie(_issued(user))).status_code == 401


def test_a_tampered_cookie_is_refused(db: Session, signed: None) -> None:
    user = _user(db)
    body, _, mac = _issued(user).partition(".")
    for forged in (f"{body}.{mac[:-2]}xx", f"{body}x.{mac}", "not-a-cookie", ""):
        assert TestClient(_gate(db)).get("/", headers=_cookie(forged)).status_code == 401


def test_a_cookie_cannot_authorize_when_the_signing_secret_is_unset(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The asymmetry is deliberate: an unsigned cookie is forgeable, so no secret
    means no cookie authorizes — while the bearer half stays OPEN with no token."""
    user = _user(db)
    value = _issued(user)
    monkeypatch.delenv(sessions.SECRET_ENV, raising=False)
    assert TestClient(_gate(db)).get("/", headers=_cookie(value)).status_code == 401


def test_a_malformed_cookie_header_is_a_refusal_not_an_error(db: Session, signed: None) -> None:
    """A header the parser cannot read carries no session cookie, so the request
    presented nothing: the API refuses it, the page sends it to the form. Neither raises."""
    client = TestClient(_gate(db), follow_redirects=False)
    for header in ("garbage", "=;;", f"{sessions.COOKIE}", "other=1"):
        assert client.get(API_WRITE, headers={"Cookie": header}).status_code == 401, header
        assert client.get("/", headers={"Cookie": header}).status_code == 303, header


def test_a_request_with_nothing_to_look_up_does_no_database_work(db: Session, signed: None) -> None:
    """No credential, no session: the gate must not open one to refuse a request.

    Nor for a bearer it can settle without the store — the shared token (which is not
    a per-user token and must not cost a query) or a header of the wrong shape.
    """

    def opened() -> AbstractContextManager[Session]:
        raise AssertionError("the gate opened a session for a request with nothing to look up")

    gate = secure.TokenGate(app, TOKEN, session_scope=opened, clock=lambda: NOW)
    # And not for the redirect either: the sign-in target is a constant, not a lookup.
    assert TestClient(gate, follow_redirects=False).get("/").status_code == 303
    assert TestClient(gate).get("/health").status_code == 200
    assert TestClient(gate).get("/static/driftless.js").status_code != 401
    bearer = TestClient(gate).get("/", headers={"Authorization": f"Bearer {TOKEN}"})
    assert bearer.status_code == 200  # the shared-token path never touches the store either
    for value in ("Bearer wrong", "Bearer ", "Basic dfl_x", "dfl_x"):
        assert TestClient(gate).get("/", headers={"Authorization": value}).status_code == 401


def test_the_authentication_surface_is_reachable_without_a_credential(db: Session) -> None:
    """A gate that hides the login page can never be signed into: with a token set,
    a browser must still reach the form or no cookie could ever come into being."""
    client = TestClient(_gate(db), follow_redirects=False)
    assert client.get("/login").status_code == 200
    # 400 is the handler's own "that form expired" — proof the POST reached login
    # rather than the gate, whose refusal is a 401 with a JSON detail body.
    assert client.post("/login", data={"username": "jp", "password": "x"}).status_code == 400
    assert client.post("/logout").status_code == 303  # clears a stale cookie, grants nothing


def test_authentication_lookalike_paths_are_still_gated(db: Session) -> None:
    """Exact match, never a prefix: /login-admin must not inherit the allowance."""
    client = TestClient(_gate(db), follow_redirects=False)
    for path in ("/login-admin", "/logoutx", "/logins", "/loginx/login"):
        assert client.get(path).status_code == 401
        assert client.post(path).status_code == 401


def test_a_viewer_reads_everything(db: Session, signed: None) -> None:
    """The gate refuses write *methods*, never pages — a viewer's GET reaches the route."""
    spy = _Spy()
    resp = TestClient(_gate(db, spy)).get("/", headers=_cookie(_issued(_user(db, role="viewer"))))
    assert (resp.status_code, spy.calls) == (204, 1)


def test_a_viewers_writes_are_refused_before_the_route(db: Session, signed: None) -> None:
    """403 at the one chokepoint, so a write route added later cannot forget to gate
    itself — and refused before the inner app is awaited, so nothing reaches the store."""
    spy = _Spy()
    client, headers = TestClient(_gate(db, spy)), _cookie(_issued(_user(db, role="viewer")))
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        resp = client.request(method, "/", headers=headers)
        assert resp.status_code == 403, method
        assert "contributor" in resp.json()["detail"]
    assert spy.calls == 0


def test_contributors_and_admins_both_write(db: Session, signed: None) -> None:
    """Ordinary writes stay open to both roles -- only the sign-off ledger narrows
    further, to admin alone (see ``_PRIVILEGED_PATHS`` below)."""
    for role in ("contributor", "admin"):
        spy = _Spy()
        user = _user(db, role=role, username=role)
        resp = TestClient(_gate(db, spy)).post("/", headers=_cookie(_issued(user)))
        assert (resp.status_code, spy.calls) == (204, 1), role


def test_a_viewer_can_still_sign_in_sign_out_and_load_static(db: Session, signed: None) -> None:
    """The trap in this unit: the open paths are decided BEFORE the role check. Get the
    order wrong and a viewer can neither reach the form, nor clear a cookie, nor load CSS."""
    headers = _cookie(_issued(_user(db, role="viewer")))
    client = TestClient(_gate(db), follow_redirects=False)
    assert client.get("/login", headers=headers).status_code == 200
    post = client.post("/login", data={"username": "jp", "password": "x"}, headers=headers)
    assert post.status_code == 400  # the handler's own "that form expired", not a gate refusal
    assert client.post("/logout", headers=headers).status_code == 303
    assert client.get("/static/driftless.js", headers=headers).status_code != 403


def test_a_bearer_token_write_is_not_role_gated(db: Session, signed: None) -> None:
    """DECIDED: the shared token resolves no principal, so it keeps full write access —
    ``DRIFTLESS_API_TOKEN`` is the bootstrap/admin credential, not an oversight."""
    spy = _Spy()
    resp = TestClient(_gate(db, spy)).post("/", headers={"Authorization": f"Bearer {TOKEN}"})
    assert (resp.status_code, spy.calls, spy.principal) == (204, 1, None)


def test_a_write_with_no_principal_and_no_token_stays_open(db: Session) -> None:
    """Dev mode is unchanged: nothing to gate on is still open, exactly as before."""
    spy = _Spy()
    assert TestClient(_gate(db, spy, token=None)).post("/").status_code == 204


def test_require_identity_refuses_anonymous_and_the_retired_shared_bearer(
    db: Session, signed: None
) -> None:
    """The mode that retires the shared credential: no bearer authorizes, only a person.

    ``token=None`` alone still means "open" (pinned above), so the two must be told
    apart — this asserts the SAME constructor argument with the flag on refuses what
    without it sails through.
    """
    spy = _Spy()
    gate = secure.TokenGate(
        spy, None, require_identity=True, session_scope=lambda: nullcontext(db), clock=lambda: NOW
    )
    client = TestClient(gate, follow_redirects=False)
    assert client.post("/").status_code == 401  # anonymous: refused, where open mode admits
    stale = client.post("/", headers={"Authorization": f"Bearer {TOKEN}"})
    assert stale.status_code == 401, "the shared bearer must not authorize in this mode"
    assert spy.calls == 0, "neither request should have reached the app"


def test_require_identity_admits_a_service_account_and_attributes_its_write(
    db: Session, signed: None
) -> None:
    """What the mode buys: the write lands with an actor instead of ``actor=None``.

    A per-user token minted for a service account is the replacement for the shared
    credential, so the principal the gate stamps is the account's — which is what
    ``api.deps._actor`` reads to credit the ChangeLog.
    """
    service = _user(db, username="importer", role="contributor")
    minted = tokens.issue(db, service, label="nightly-import")
    spy = _Spy()
    gate = secure.TokenGate(
        spy, None, require_identity=True, session_scope=lambda: nullcontext(db), clock=lambda: NOW
    )
    resp = TestClient(gate).post("/", headers={"Authorization": f"Bearer {minted}"})
    assert (resp.status_code, spy.calls) == (204, 1)
    assert spy.principal == Principal(uid=service.id, username="importer", role="contributor")


def test_create_secured_app_requires_a_user_credential_when_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(secure.TOKEN_ENV, raising=False)
    monkeypatch.delenv(secure.LEGACY_TOKEN_ENV, raising=False)
    monkeypatch.setenv(secure.REQUIRE_USER_AUTH_ENV, "1")
    gated = secure.create_secured_app()
    assert gated._token is None and gated._require_identity is True


def test_create_secured_app_refuses_both_credential_modes_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refused rather than resolved: either the operator believes the shared credential
    still works or believes this mode is on, and silently picking one leaves a wrong
    mental model about what authorizes."""
    monkeypatch.setenv(secure.TOKEN_ENV, TOKEN)
    monkeypatch.setenv(secure.REQUIRE_USER_AUTH_ENV, "1")
    with pytest.raises(RuntimeError, match=secure.REQUIRE_USER_AUTH_ENV):
        secure.create_secured_app()


def test_the_read_methods_and_the_writing_roles_are_pinned(db: Session, signed: None) -> None:
    """Pinned as behaviour, not as a comment: a method silently added to the read set,
    or a role silently given the write, fails here. Every role is accounted for."""
    assert secure._READ_METHODS == frozenset({"GET", "HEAD", "OPTIONS"})
    assert secure._WRITE_ROLES == frozenset({"admin", "contributor"})
    assert secure._PRIVILEGED_PATHS == frozenset({SIGN_OFF_JSON, SIGN_OFF_PAGE, SIGN_OFF_VERSIONED})
    assert set(USER_ROLES) - secure._WRITE_ROLES == {"viewer"}
    spy = _Spy()  # and an unlisted method is a write, not a read: fail closed
    headers = _cookie(_issued(_user(db, role="viewer")))
    resp = TestClient(_gate(db, spy)).request("TRACE", "/", headers=headers)
    assert (resp.status_code, spy.calls) == (403, 0)


def test_the_gate_uses_the_apps_own_lazy_factory_by_default() -> None:
    """No second engine against the one SQLite file — the app's session dependency."""
    assert secure.TokenGate(app, TOKEN)._session_scope is secure.session_scope


def _viewer(db: Session) -> dict[str, str]:
    return _cookie(_issued(_user(db, role="viewer")))


def test_a_viewers_write_to_a_page_gets_the_designed_refusal(db: Session, signed: None) -> None:
    """The gate runs before routing, so its refusal reaches no exception handler: a
    browser submitting a form used to be answered with the raw JSON body."""
    resp = TestClient(_gate(db)).post(PAGE_WRITE, headers=_viewer(db))
    assert resp.status_code == 403
    assert resp.headers["content-type"].startswith("text/html")
    assert 'href="/threats"' in resp.text  # the designed shell, not a bare message
    assert "403" in resp.text
    # Its own wording: this reader is signed in as a viewer, not looking at a stale form.
    assert "viewer" in resp.text and "contributor access" in resp.text
    assert "expired" not in resp.text
    assert secure._WRITE_DENIED.decode() not in resp.text  # and no JSON detail leaked


def test_the_json_api_refusal_stays_the_same_bytes(db: Session, signed: None) -> None:
    """Pinned as a literal so a later refactor cannot quietly HTML-ify the API."""
    resp = TestClient(_gate(db)).post(API_WRITE, headers=_viewer(db), json={})
    assert resp.status_code == 403
    assert resp.content == b'{"detail":"writes need the contributor or admin role"}'
    assert resp.headers["content-type"] == "application/json"


def test_a_signed_out_browser_at_a_page_lands_on_the_sign_in_form(db: Session) -> None:
    """The dead end this unit removes: the gate runs before routing, so a browser with
    no cookie was handed the API's JSON body at an address a person had typed."""
    client = TestClient(_gate(db), follow_redirects=False)
    for path in ("/", PAGE_WRITE):
        resp = client.get(path)
        assert (resp.status_code, resp.headers["location"]) == (303, "/login"), path
        assert UNAUTHENTICATED.decode() not in resp.text, path
    # A form posted from a page whose session died gets the same 303, which a browser
    # follows as a GET — which is why 303, and it is the login router's own idiom.
    assert client.post(PAGE_WRITE).status_code == 303


def test_the_json_401_is_the_same_bytes_on_every_other_surface(db: Session) -> None:
    """Pinned as a literal, never as a status: a script's refusal must not move a byte."""
    client = TestClient(_gate(db), follow_redirects=False)
    for path in (API_WRITE, "/health/ready", "/static-export", "/login-admin"):
        resp = client.post(path)
        assert resp.status_code == 401, path
        assert resp.content == UNAUTHENTICATED, path
        assert resp.headers["content-type"] == "application/json", path


def test_a_page_request_carrying_a_credential_is_refused_not_redirected(
    db: Session, signed: None
) -> None:
    """The redirect answers "you presented nothing". A credential that was rejected is a
    different answer and keeps the JSON 401 — a form cannot fix a bad token.

    DECIDED, the case that had to be chosen: a live cookie whose epoch the store has
    moved past — what ``driftless user disable`` leaves behind — counts as presented, so
    401. The gate cannot tell it from a forgery without plumbing a reason out of
    ``principal.resolve``, and a disabled account sent to a form that will refuse it is
    exactly the loop this rule exists to prevent. Ordinary expiry still reaches the form:
    the cookie's ``max-age`` is the session TTL, so a browser has dropped it by the time
    the signature goes stale and the next request presents nothing at all.
    """
    user = _user(db)
    stale = _issued(user)
    user.session_epoch += 1  # exactly what ``driftless user disable`` does
    db.commit()
    client = TestClient(_gate(db), follow_redirects=False)
    for headers in (
        {"Authorization": "Bearer wrong"},
        {"Authorization": "Basic dfl_x"},
        _cookie("not-a-cookie"),
        _cookie(""),
        _cookie(stale),
    ):
        resp = client.get("/", headers=headers)
        assert (resp.status_code, resp.content) == (401, UNAUTHENTICATED), headers


def test_the_redirect_can_be_pointed_nowhere_but_login(db: Session) -> None:
    """No ``?next=``: a return path taken from the request is an open redirect, and
    validating one properly is more surface than saving a click. So nothing a caller
    sends — query, headers or the address itself — moves the target off ``/login``,
    which is itself an open path, so the landing can never be refused in a loop."""
    client = TestClient(_gate(db), follow_redirects=False)
    hostile = {"Referer": "https://evil.example/x", "X-Forwarded-Host": "evil.example"}
    for path in ("/", "/?next=https://evil.example", "/?next=//evil.example"):
        assert client.get(path, headers=hostile).headers["location"] == "/login", path
    assert secure._LOGIN_PATH == "/login" and secure._LOGIN_PATH in secure._AUTH_PATHS


def test_the_403_page_and_the_open_paths_survive_the_redirect(db: Session, signed: None) -> None:
    """#1624's refusal is untouched, and the open paths still answer themselves — a
    redirect at ``/login`` would be the loop, one at ``/health`` an unprobeable container."""
    client = TestClient(_gate(db), follow_redirects=False)
    refused = client.post(PAGE_WRITE, headers=_viewer(db))
    assert refused.status_code == 403 and refused.headers["content-type"].startswith("text/html")
    assert client.get("/health").content == b'{"status":"ok"}'
    assert client.get("/static/driftless.js").status_code not in (303, 401)
    assert client.get("/login").status_code == 200


def test_a_contributor_is_untouched_on_both_surfaces(db: Session, signed: None) -> None:
    """Never refused at the gate, so the page POST reaches the route — whose own CSRF
    403 keeps its own wording, which is the drift the shared helper prevents."""
    client = TestClient(_gate(db), follow_redirects=False)
    headers = _cookie(_issued(_user(db, role="contributor", username="cc")))
    page = client.post(PAGE_WRITE, headers=headers)
    assert "expired" in page.text and "contributor access" not in page.text
    assert client.post(API_WRITE, headers=headers, json={}).content != secure._WRITE_DENIED


def test_the_open_paths_are_untouched_by_the_page_refusal(db: Session, signed: None) -> None:
    """Decided before the role check, so no page shell can reach them."""
    client = TestClient(_gate(db), follow_redirects=False)
    headers = _viewer(db)
    assert client.get("/health", headers=headers).content == b'{"status":"ok"}'
    assert client.get("/static/driftless.js", headers=headers).status_code != 403
    form = client.post("/login", data={"username": "jp", "password": "x"}, headers=headers)
    assert form.status_code == 400  # the handler's own expired-form page, not the gate
    assert client.post("/logout", headers=headers).status_code == 303


def test_an_unreadable_route_table_falls_back_to_the_json_body(db: Session, signed: None) -> None:
    """A gate that 500s is worse than a gate that answers JSON: an inner app exposing
    no routes still refuses, and still refuses before the inner app is awaited."""
    spy = _Spy()
    resp = TestClient(_gate(db, spy)).post(PAGE_WRITE, headers=_viewer(db))
    assert (resp.status_code, resp.content, spy.calls) == (403, secure._WRITE_DENIED, 0)


def test_the_gate_finds_the_pages_nested_inside_the_included_routers() -> None:
    """Guard against a vacuous pass: the page routers hang off wrapper routes, so a
    walk of the app's top level alone finds none of them and every refusal stays JSON.
    Rebuilt by constructing a gate — the walk is per instance, never a module cache."""
    pages = secure.TokenGate(app, TOKEN)._pages
    assert any(pattern.match(PAGE_WRITE) for pattern in pages), len(pages)
    assert not any(pattern.match(API_WRITE) for pattern in pages)


def _bearer(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def _minted(db: Session, user: User) -> dict[str, str]:
    """A live per-user token, presented the way an agent or a script presents it."""
    return _bearer(tokens.issue(db, user, label="ci"))


def test_a_per_user_token_admits_and_stamps_its_owner(db: Session) -> None:
    """The payoff: a token resolves to the SAME principal a cookie yields, so role
    gating and the per-user audit actor both light up with no second mechanism.

    No signing secret is set here — the token half is independent of the cookie half.
    """
    spy = _Spy()
    user = _user(db, role="contributor", username="agent")
    resp = TestClient(_gate(db, spy)).get("/", headers=_minted(db, user))
    assert (resp.status_code, spy.calls) == (204, 1)
    assert spy.principal == Principal(uid=user.id, username="agent", role="contributor")


def test_a_revoked_token_is_refused(db: Session) -> None:
    """``tokens.resolve`` reads the row back; the gate re-implements none of that.

    The same token, the same client, before and after — so the refusal is revocation
    working and not some other reason this request would have been turned away.
    """
    spy = _Spy()
    client, headers = TestClient(_gate(db, spy)), _minted(db, _user(db))
    assert client.get("/", headers=headers).status_code == 204
    assert tokens.revoke(db, db.scalars(select(ApiToken.id)).one()) is True
    assert (client.get("/", headers=headers).status_code, spy.calls) == (401, 1)


def test_a_deactivated_users_token_is_refused(db: Session) -> None:
    """Disabling a user kills every token they hold, as the epoch does every cookie."""
    user = _user(db)
    client, headers = TestClient(_gate(db)), _minted(db, user)
    assert client.get("/", headers=headers).status_code == 200
    user.is_active = False  # exactly what ``driftless user disable`` does
    db.commit()
    assert client.get("/", headers=headers).status_code == 401


def test_a_garbage_or_wrong_shaped_bearer_is_a_refusal_not_an_error(db: Session) -> None:
    """Every shape that is not a live token fails closed, and none of them raises.

    The scheme is matched exactly, as the shared-token compare already does: a
    stricter gate is the fail-closed one.
    """
    live = tokens.issue(db, _user(db), label="ci")
    client = TestClient(_gate(db))
    for value in ("Bearer", "Bearer ", f"Bearer {live}x", f"Bearer {live[:-1]}", f"bearer {live}"):
        assert client.get("/", headers={"Authorization": value}).status_code == 401, value
    for value in (f"Basic {live}", "Bearer dfl_nope", "Bearer not-a-token", "", "   "):
        assert client.get("/", headers={"Authorization": value}).status_code == 401, value


def test_a_viewers_token_reads_everything_and_writes_nothing(db: Session) -> None:
    """Held to its owner's role exactly as their cookie is — which is what makes a
    viewer's token a read-only credential with nothing extra to configure."""
    spy = _Spy()
    client = TestClient(_gate(db, spy))
    headers = _minted(db, _user(db, role="viewer"))
    assert client.get("/", headers=headers).status_code == 204
    refused = client.post(API_WRITE, headers=headers, json={})
    assert (refused.status_code, refused.content) == (403, secure._WRITE_DENIED)
    assert spy.calls == 1  # the read reached the app; the write never did


def test_a_token_still_resolves_with_no_shared_token_configured(db: Session) -> None:
    """Open development mode *withholds* nothing — but it must not forget who is
    asking, or a viewer's token would silently gain writes and the actor would vanish."""
    spy = _Spy()
    client = TestClient(_gate(db, spy, token=None))
    viewer = _user(db, role="viewer")
    assert client.get("/", headers=_minted(db, viewer)).status_code == 204
    assert spy.principal == Principal(uid=viewer.id, username="jp", role="viewer")
    assert (client.post("/", headers=_minted(db, viewer)).status_code, spy.calls) == (403, 1)


def test_a_cookie_wins_when_a_cookie_and_a_bearer_both_arrive(db: Session, signed: None) -> None:
    """DECIDED: both present, the cookie decides. So attaching a header can never DROP
    a browser's identity, and every request carrying a cookie behaves exactly as it did
    before tokens were accepted — this unit can only add admissions, never change one."""
    spy = _Spy()
    viewer = _user(db, role="viewer")
    headers = _cookie(_issued(viewer)) | _minted(db, _user(db, role="admin", username="agent"))
    assert TestClient(_gate(db, spy)).get("/", headers=headers).status_code == 204
    assert spy.principal == Principal(uid=viewer.id, username="jp", role="viewer")
    # And the consequence that matters: the admin token does not lift the viewer's gate.
    assert TestClient(_gate(db, spy)).post("/", headers=headers).status_code == 403


def test_the_gate_stamps_which_credential_authenticated(db: Session, signed: None) -> None:
    """Beside the principal, the fact CSRF turns on: a cookie is ambient — a browser
    attaches it to whatever another origin causes — and a bearer header never is.

    The strings are the contract between the gate and the form POSTs that read them, so
    they are spelled out here rather than read off the module. The both-arrive row is the
    load-bearing one: the cookie wins, so attaching a header cannot drop a browser's pair.
    """
    cookie = _cookie(_issued(_user(db)))
    bearer = _minted(db, _user(db, role="admin", username="agent"))
    for headers, kind in (
        (cookie, "cookie"),
        (bearer, "token"),
        (_bearer(TOKEN), "shared"),
        (cookie | bearer, "cookie"),
        ({}, None),  # dev mode admits with nothing resolved, so the pair stays required
    ):
        spy = _Spy()
        gate = _gate(db, spy, token=TOKEN if headers else None)
        assert TestClient(gate).get("/", headers=headers).status_code == 204, kind
        assert spy.credential == kind, headers


@pytest.fixture
def audited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    """The app's OWN lazy factory, changelog listener and all — no dependency override,
    because the override replaces the very dependency that stamps the audit actor."""
    engine = new_engine(f"sqlite:///{tmp_path / 'audited.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    monkeypatch.setattr(db_session, "_factory", factory)
    yield factory


def test_a_write_authorized_by_a_token_is_credited_to_its_owner(
    audited: sessionmaker[Session],
) -> None:
    """The claim this unit is really making, end to end: token -> principal -> session
    actor -> ChangeLog row. Nothing is injected; the gate takes its default scope, so
    this also proves the gate and the routes share the one factory."""
    with audited() as setup:
        headers = _minted(setup, _user(setup, role="contributor", username="agent"))
    client = TestClient(secure.TokenGate(app, TOKEN), headers=headers)

    created = client.post("/businesses", json={"name": "Token Write"})

    assert created.status_code == 201, created.text
    with audited() as db:
        rows = db.scalars(select(ChangeLog).where(ChangeLog.table_name == "business")).all()
    assert [row.actor for row in rows] == ["agent"]


def test_a_contributor_cannot_sign_off_through_the_json_route(db: Session, signed: None) -> None:
    """A sign-off is a governance act, not an edit: contributor is enough for every
    other write and not enough for this one -- and its own wording, not the ordinary
    write refusal's, since a contributor already holds the role that message names."""
    spy = _Spy()
    headers = _cookie(_issued(_user(db, role="contributor", username="cc")))
    resp = TestClient(_gate(db, spy)).post(SIGN_OFF_JSON, headers=headers, json={})
    assert (resp.status_code, resp.content, spy.calls) == (403, secure._PRIVILEGED_DENIED, 0)


def test_a_contributor_cannot_sign_off_through_the_page_form_either(
    db: Session, signed: None
) -> None:
    """The hole this unit closes: the browser form calls ``create_sign_off`` too
    rather than assembling its own row (driftless/services/sign_offs.py),
    so gating only the JSON address would leave a second, unlocked way to the same write.
    ``inner=app`` (the ``_gate`` default), so ``self._pages`` matches the real page
    patterns -- the refusal is decided before ``self._inner`` is ever awaited, so no
    route runs regardless."""
    headers = _cookie(_issued(_user(db, role="contributor", username="cc")))
    resp = TestClient(_gate(db), follow_redirects=False).post(SIGN_OFF_PAGE, headers=headers)
    assert resp.status_code == 403
    assert resp.headers["content-type"].startswith("text/html")  # a browser form, not JSON
    # And its OWN wording. The viewer page would tell this reader to ask for the
    # contributor access they already hold — a dead end, not merely clumsy copy.
    assert "administrator" in resp.text
    assert "viewer" not in resp.text and "contributor access" not in resp.text


def test_a_viewer_refused_at_a_privileged_address_still_reads_the_viewer_refusal(
    db: Session, signed: None
) -> None:
    """The other side of that split, and why it keys on the ROLE rather than the path.
    A viewer at the sign-off form is refused by the write floor, not by the admin tier:
    they cannot write anything, so "ask an admin to sign this off" would name the one
    thing that is not their problem. Both surfaces agree — the page keeps its read-only
    wording and the JSON keeps the ordinary write refusal, byte for byte."""
    client, headers = TestClient(_gate(db), follow_redirects=False), _viewer(db)
    page = client.post(SIGN_OFF_PAGE, headers=headers)
    assert (page.status_code, "contributor access" in page.text) == (403, True)
    api = client.post(SIGN_OFF_JSON, headers=headers, json={})
    assert (api.status_code, api.content) == (403, secure._WRITE_DENIED)


def test_an_admin_reaches_the_sign_off_route(audited: sessionmaker[Session]) -> None:
    """The other half of the claim: admin is not merely let past the gate, the write
    lands -- proving the narrowed tier still admits the role meant to keep it."""
    with audited() as setup:
        headers = _minted(setup, _user(setup, role="admin", username="jp"))
    client = TestClient(secure.TokenGate(app, TOKEN), headers=headers)
    resp = client.post(
        SIGN_OFF_JSON,
        json={"subject_kind": "threat", "subject_ref": "x", "decision": "accepted"},
    )
    assert resp.status_code == 201, resp.text


def _reaches(endpoint: object, target: object) -> bool:
    """Whether ``endpoint`` IS ``target``, or calls it directly in its own body."""
    if endpoint is target:
        return True
    try:
        source = textwrap.dedent(inspect.getsource(endpoint))  # type: ignore[arg-type]
    except (OSError, TypeError):
        return False
    tree = ast.parse(source)
    name = getattr(target, "__name__", None)
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
        for node in ast.walk(tree)
    )


def _routes_writing_a_sign_off() -> frozenset[str]:
    """Every live write-method route on ``app`` that reaches ``create_sign_off`` --
    derived from the REAL route table and each handler's own source, never a
    hand-typed path, so this is the independent half of the exact-set check below."""
    return frozenset(
        leaf.path
        for route in app.routes
        for leaf in secure._leaves(route)
        if isinstance(leaf, APIRoute)
        and set(leaf.methods or ()) - secure._READ_METHODS
        and _reaches(leaf.endpoint, create_sign_off)
    )


def test_the_privileged_paths_are_exactly_the_routes_that_write_a_sign_off() -> None:
    """The exact-set idiom this repo already uses twice (``NOT_CHOOSING_A_PLAN``,
    ``tests/test_baseline_selection.py``): a route reaching ``create_sign_off`` that
    ``secure._PRIVILEGED_PATHS`` has not named, or a name it still carries after the
    route it named is gone, both fail here rather than drift quietly."""
    derived = _routes_writing_a_sign_off()
    assert derived == {SIGN_OFF_JSON, SIGN_OFF_PAGE, SIGN_OFF_VERSIONED}  # not a vacuous walk
    assert derived == secure._PRIVILEGED_PATHS, sorted(derived ^ secure._PRIVILEGED_PATHS)
