"""Every web form POST is CSRF-bound — walked off the real app, not listed by hand.

The router half enumerates every POST route the web routers contribute to
``driftless.api.app.app`` and replays that page's OWN rendered form with no token, a
stale one, another browser's, and with the cookie half stripped: each refused 403
with every table's row count untouched, while the real pair still writes and
redirects where it always did. The only exemption is ``/login``; ``/logout`` is bound
too, and its tests assert the epoch, because a forged sign-out revokes every device.
The template half matters as much: a route checking a token whose form never renders
one would 403 forever while the router walk stayed green — so a second walk loads
EVERY page the app registers and reads the token back out of the sign-out form.

The last tests run the gated app, where the pair is required only where forgery is
possible: a wizard apply authenticated by a bearer token skips it (and is credited to
the token's owner), while a cookie one — including a cookie that carries a header too —
still pairs, and every other form is walked to prove the exemption did not widen.

One test states what CSRF costs the byte-identical-regeneration property: a
cookie-less refetch moves by exactly its token and by nothing else.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from driftless.api import app as app_module
from driftless.api.app import app as real_app
from driftless.api.secure import TokenGate
from driftless.auth import sessions, tokens
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import ChangeLog, register_changelog
from driftless.models import Department, Program, Project, User
from driftless.pmbok import catalog
import test_web_pages
from test_web_pages import AS_OF
from test_web_routes_not_shadowed import _included, _leaves, _shape

# The seeded https store, reused as is (assigned, not imported: a test's own
# ``client``/``db`` parameter must not read as a redefined import).
client, db = test_web_pages.client, test_web_pages.db

Q = f"?as_of={AS_OF.isoformat()}"

# Each protected POST against the page rendering its form: the body posted below IS
# that form, so a route is only exercised the way a browser posts it. ``{}`` is the
# shape ``_shape`` normalises to, the seed's one project is id 1, and each redirects
# back to its own page — so these values pin the redirect target too.
WIZARD = "/projects/{}/wizard/apply"
PAGES = {
    "/sign-off": f"/threats{Q}",
    WIZARD: f"/projects/1/wizard{Q}",
    "/projects/{}/status": f"/projects/1/status{Q}",
}
# The pair is required only where CSRF is a threat, so a request authenticated by a bearer
# token skips it — and only here: every other web POST already has a JSON API route
# (``/sign-offs``, ``/status-snapshots``), while the wizard's write side has none, which is
# the gap that left an agent no path to it at all.
TOKEN_WRITES = frozenset({WIZARD})
# The name is posted because the producer refuses without it: a body the write side would
# refuse tests nothing about CSRF.
APPLY = {"kind": "stakeholder_register", "as_of": AS_OF.isoformat(), "name": "Ada Lovelace"}
# /login mints a fresh pair per GET, so its POST checks the pair it handed out. /logout
# is bound too, but is no PAGES-shaped write (it redirects to /login and writes no row),
# so the sign-out tests below pin its pair rather than the table above.
EXEMPT = frozenset({"/login"})
SIGN_OUT = "/logout"
# One reachable id per parameterised page shape; a router added later joins this table.
_PER_PROJECT = ("board", "gantt", "hub", "process-map", "status", "wizard")
SAMPLE = {f"/projects/{{}}/{p}": "1" for p in _PER_PROJECT}
SAMPLE |= {"/pmbok/{}": catalog.PROCESSES[0].id, "/org/departments/{}": "1"}
SAMPLE |= {"/portfolios/{}/rollup": "1", "/programs/{}/rollup": "1"}
SECRET = "test-signing-secret"  # pragma: allowlist secret  (throwaway in-test signing key)
SHARED = "shared-bootstrap-token"  # pragma: allowlist secret  (in-test gate token)
_DROPPED = f'{sessions.COOKIE}=""'  # how a response says it is clearing the session

_FORM = re.compile(r'<form[^>]*method="post"[^>]*action="([^"]+)"[^>]*>(.*?)</form>', re.S)
_NAMED = re.compile(r'<(input|select|textarea)[^>]*\bname="([^"]+)"(?:[^>]*\bvalue="([^"]*)")?')
_OPTION = re.compile(r'<option value="([^"]*)"')
TYPED = "sample prose"  # what these walks "type" into a textarea; see _forms below
_TOKEN_VALUE = re.compile(r'name="csrf_token" value="[^"]*"')


def _untokened(html: str) -> str:
    """``html`` with every CSRF field's value blanked — the page minus its per-visitor half."""
    return _TOKEN_VALUE.sub('name="csrf_token" value=""', html)


def _forms(html: str) -> list[tuple[str, dict[str, str]]]:
    """Each ``method="post"`` form as ``(action, body)``: what a browser submits."""
    forms = []
    for action, inner in _FORM.findall(html):
        body: dict[str, str] = {}
        for field in _NAMED.finditer(inner):
            tag, name, value = field.group(1), field.group(2), field.group(3) or ""
            if tag == "select":
                option = _OPTION.search(inner, field.end())
                value = option.group(1) if option else ""
            elif tag == "textarea":
                # A filled-in form, exactly as the select above is read as its first
                # option: the wizard's prose field refuses a blank body, and a walk
                # posting one would be asserting that refusal rather than the CSRF
                # outcome it is here for.
                value = value or TYPED
            body.setdefault(name, value)
        forms.append((action, body))
    return forms


def _web_paths(method: str) -> set[str]:
    """Shapes of every ``method`` route the web routers add (CRUD is registered directly)."""
    paths: set[str] = set()
    for route in real_app.routes:
        for child in _included(route) or ():
            for leaf in _leaves(child):
                if method in (getattr(leaf, "methods", None) or ()):
                    paths.add(_shape(str(getattr(leaf, "path", ""))))
    return paths


def test_the_only_csrf_exemption_is_the_login_form() -> None:
    posts = _web_paths("POST")
    assert EXEMPT == frozenset({"/login"}), "the exemption set is pinned, not grown"
    assert EXEMPT <= posts and SIGN_OUT in posts, sorted(posts)
    assert sorted(posts - EXEMPT - {SIGN_OUT}) == sorted(PAGES), (
        "a web POST route with no PAGES entry is untested for CSRF: register the page whose form "
        "posts to it, or add it to EXEMPT with the reason it grants an attacker nothing."
    )


def _census(session: Session) -> dict[str, int]:  # a refused POST changes none of these
    return {
        table.name: session.scalar(select(func.count()).select_from(table)) or 0
        for table in Base.metadata.sorted_tables
    }


def _form_for(browser: TestClient, shape: str) -> tuple[str, dict[str, str]]:
    """The rendered form posting to ``shape``: its action and its default body."""
    action = shape.replace("{}", "1")
    page = browser.get(PAGES[shape])
    assert page.status_code == 200, page.text
    bodies = [body for posts_to, body in _forms(page.text) if posts_to == action]
    assert bodies, f"{PAGES[shape]} renders no form posting to {action}"
    return action, bodies[0]


@pytest.mark.parametrize("page", sorted({"/", *PAGES.values()}))
def test_every_rendered_form_has_a_token(client: TestClient, page: str) -> None:
    rendered = client.get(page)
    assert rendered.status_code == 200, rendered.text
    forms = [(a, body) for a, body in _forms(rendered.text) if a not in EXEMPT]
    assert forms, f"{page} renders no protected POST form, so this test proves nothing"
    for action, body in forms:
        assert body.get("csrf_token"), f"{page}'s form posting to {action} carries no token"


@pytest.fixture
def signed_in(client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> User:
    """A real user whose real signed cookie is in the jar — what a sign-out revokes."""
    monkeypatch.setenv(sessions.SECRET_ENV, SECRET)
    user = User(username="jp", password_hash="unused", role="admin")
    db.add(user)
    db.commit()
    live = datetime(2099, 1, 1, tzinfo=UTC)
    value = sessions.issue(user.id, user.username, user.role, live, SECRET, user.session_epoch)
    client.cookies.set(sessions.COOKIE, value)
    return user


def _sign_out_form(browser: TestClient, page: str) -> dict[str, str]:  # as the nav posts it
    bodies = [body for action, body in _forms(browser.get(page).text) if action == SIGN_OUT]
    assert bodies, f"{page} renders no sign-out form"
    return bodies[0]


@pytest.mark.parametrize("shape", sorted(_web_paths("GET")))
def test_every_page_the_app_registers_renders_the_sign_out_forms_token(
    client: TestClient, db: Session, shape: str
) -> None:
    """``base.html`` renders the sign-out form on EVERY page, so every page-rendering
    router must attach a pair — walked off the app's route table, so a router added
    next year is walked the day it is mounted."""
    assert "{}" not in shape or shape in SAMPLE, f"{shape} needs a reachable id in SAMPLE"
    project = db.scalars(select(Project)).one()  # the rows the seed lacks, so no shape 404s
    project.program = Program(name="Reels", portfolio=project.portfolio)
    db.add(Department(name="Post", business=project.portfolio.business))
    db.commit()
    client.cookies.set(sessions.COOKIE, "anything")  # the nav renders sign-out on presence
    path = shape.replace("{}", SAMPLE.get(shape, ""))
    assert client.get(path).status_code == 200, path
    assert _sign_out_form(client, path).get("csrf_token"), (
        f"{shape} renders the sign-out form with no token, so signing out from it 403s"
    )


def test_only_a_paired_sign_out_revokes_and_a_pairless_one_clears_this_browser_only(
    client: TestClient, signed_in: User
) -> None:
    """The harm the exemption carried: sign-out bumps ``session_epoch``, revoking the
    victim on EVERY device — so assert the store, not just the status. The pairless POST
    is DECIDED and the one refusal that is not a 403: no cookie half means never handed
    a pair, so it gets only the half that grants an attacker nothing."""
    before = signed_in.session_epoch
    cleared = client.post(SIGN_OUT, follow_redirects=False)  # no cookie half yet: no pair
    assert cleared.status_code == 303 and _DROPPED in cleared.headers["set-cookie"]
    assert signed_in.session_epoch == before, "a pairless sign-out revoked every device"

    body = _sign_out_form(client, "/")  # ...and now the browser holds one
    for reading, token in {"none": "", "stale": f"{body['csrf_token']}-expired"}.items():
        refused = client.post(SIGN_OUT, data={"csrf_token": token}, follow_redirects=False)
        assert refused.status_code == 403, f"{reading} token: {refused.status_code}"
        assert signed_in.session_epoch == before, f"a {reading}-token sign-out revoked the user"
        assert "expired" in refused.text, "a refused sign-out renders the designed page"
    accepted = client.post(SIGN_OUT, data=body, follow_redirects=False)  # the page's own pair
    assert accepted.status_code == 303 and accepted.headers["location"] == "/login"
    assert signed_in.session_epoch == before + 1, "the genuine sign-out revoked nothing"
    assert _DROPPED in accepted.headers["set-cookie"], "this browser kept its session cookie"


def test_one_browser_reuses_its_token_while_login_still_mints_per_render(
    client: TestClient, signed_in: User
) -> None:
    walk = (f"/threats{Q}", "/", "/login", "/login", f"/threats{Q}")
    board, home, first, second, again = (_sign_out_form(client, p)["csrf_token"] for p in walk)
    assert board == home, "a second render invalidated the first tab's open form"
    assert first != second, "/login must still mint a FRESH pair per render"
    assert again == second, "every other page reuses the pair the browser holds"


@pytest.mark.parametrize("shape", sorted(PAGES))
def test_only_the_pages_own_pair_is_accepted_and_a_refusal_writes_nothing(
    client: TestClient, db: Session, shape: str
) -> None:
    action, body = _form_for(client, shape)
    with TestClient(real_app, base_url="https://testserver") as other:  # its own jar+pair
        foreign = _form_for(other, shape)[1]["csrf_token"]
    bad = {"no": "", "stale": f"{body['csrf_token']}-expired", "foreign": foreign}
    before = _census(db)
    for reading, token in bad.items():
        refused = client.post(action, data=body | {"csrf_token": token}, follow_redirects=False)
        assert refused.status_code == 403, f"{reading} token on {action}: {refused.status_code}"
        assert _census(db) == before, f"{reading} token on {action} reached the store"
    accepted = client.post(action, data=body, follow_redirects=False)  # the page's real pair
    assert accepted.status_code == 303, accepted.text
    assert accepted.headers["location"] == PAGES[shape], "the redirect target is unchanged"
    assert sum(_census(db).values()) > sum(before.values()), "the write landed"
    client.cookies.clear()  # the field alone, with no cookie half to match it
    written = _census(db)
    assert client.post(action, data=body, follow_redirects=False).status_code == 403
    assert _census(db) == written, f"a cookie-less POST to {action} reached the store"


@pytest.mark.parametrize("page", sorted({"/", *PAGES.values()}))
def test_the_token_is_the_only_thing_a_cookieless_refetch_changes(
    client: TestClient, page: str
) -> None:
    """Byte-identical regeneration, stated the way CSRF actually leaves it.

    A visitor holding no cookie has to be issued one, so ``csrf.ensure`` mints per
    render and the two pages cannot be byte-equal — that is the mechanism working, not
    a defect. What must still hold is that the token is the *only* thing that moves:
    everything computed from the store is byte-identical for a pinned as-of. So this
    asserts both halves — equal once the token values are blanked, and genuinely
    unequal before, which is what stops the normaliser from quietly passing a page
    that renders no token at all.
    """
    with TestClient(real_app) as cookieless:  # plain http: the Secure cookie never returns
        first, second = (cookieless.get(page).text for _ in range(2))
    assert _untokened(first) == _untokened(second), (
        f"{page} moved for a reason other than the token"
    )
    assert first != second, f"{page} renders no per-visitor token, so this proves nothing"


class Gate(NamedTuple):
    """The gated app and the credentials an agent or a browser reaches it with."""

    app: TokenGate
    factory: sessionmaker[Session]
    token: str  # a contributor's per-user bearer
    viewer: str  # a viewer's
    cookie: str  # the same contributor's signed session cookie


@pytest.fixture
def gated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Gate]:
    """The real gate over the real app, on the app's OWN session dependency — no override,
    because the override replaces the very dependency that credits the audit actor."""
    monkeypatch.setenv(sessions.SECRET_ENV, SECRET)
    engine = new_engine(f"sqlite:///{tmp_path / 'gated.db'}")
    Base.metadata.create_all(engine)
    register_changelog(factory := new_session_factory(engine))
    monkeypatch.setattr(app_module, "_factory", factory)
    with factory() as setup:
        test_web_pages._seed(setup)  # the same seed the browser half walks: one project, one threat
        agent = User(username="agent", password_hash="x", role="contributor")
        reader = User(username="reader", password_hash="x", role="viewer")
        setup.add_all([agent, reader])
        setup.commit()
        live = datetime(2099, 1, 1, tzinfo=UTC)
        yield Gate(
            TokenGate(real_app, SHARED),
            factory,
            tokens.issue(setup, agent, label="agent-loop"),
            tokens.issue(setup, reader, label="read-only"),
            sessions.issue(agent.id, agent.username, agent.role, live, SECRET, agent.session_epoch),
        )


def _client(gate: Gate, **headers: str) -> TestClient:
    """A client presenting exactly ``headers`` — https, as production serves."""
    return TestClient(
        gate.app, base_url="https://testserver", headers=headers, follow_redirects=False
    )


def _credited(gate: Gate) -> list[str | None]:
    """The actor on every ChangeLog row the wizard's stakeholder write leaves behind."""
    with gate.factory() as db:
        rows = select(ChangeLog.actor).where(ChangeLog.table_name == "stakeholder")
        return list(db.scalars(rows))


def test_a_tokens_wizard_write_needs_no_pair_and_is_credited_to_its_owner(gated: Gate) -> None:
    """The gap the agent guide had to write down instead of closing. CSRF works because a
    browser attaches an AMBIENT credential — a cookie — to a request another origin caused;
    a bearer token is attached deliberately and no cross-origin page can make a browser send
    one, so the pair has nothing left to prove and a token client can drive the loop."""
    agent = _client(gated, Authorization=f"Bearer {gated.token}")
    applied = agent.post(WIZARD.format(1), data=APPLY)
    assert applied.status_code == 303, applied.text
    assert applied.headers["location"] == f"/projects/1/wizard?as_of={AS_OF.isoformat()}"
    assert _credited(gated) == ["agent"], "the write did not name the token's owner"


def test_a_cookie_request_still_pairs_even_when_a_bearer_rides_along(gated: Gate) -> None:
    """The load-bearing case: #1628 gives the cookie precedence when both arrive, so a
    browser that also sends a header is a COOKIE request and still pairs. Backwards, and
    CSRF is bypassable by adding one header."""
    browser = _client(gated)
    browser.cookies.set(sessions.COOKIE, gated.cookie)
    riding = {"Authorization": f"Bearer {gated.token}"}
    for reading, extra in {"cookie": {}, "cookie+bearer": riding}.items():
        refused = browser.post(WIZARD.format(1), data=APPLY, headers=extra)
        assert refused.status_code == 403, f"{reading}: {refused.status_code}"
        assert _credited(gated) == [], f"{reading}: a pairless POST reached the store"
    action, body = _form_for(browser, WIZARD)  # ...and the page's own pair still writes
    assert browser.post(action, data=body, headers=riding).status_code == 303


def test_a_viewers_token_is_refused_the_wizard_write(gated: Gate) -> None:
    """Role gating is untouched: the exemption is about CSRF, never about who may write."""
    reader = _client(gated, Authorization=f"Bearer {gated.viewer}")
    refused = reader.post(WIZARD.format(1), data=APPLY)
    assert refused.status_code == 403
    assert _credited(gated) == [], "a viewer's token reached the store"


@pytest.mark.parametrize("shape", sorted(PAGES))
def test_a_token_still_pairs_on_every_form_but_the_wizards(gated: Gate, shape: str) -> None:
    """Structural, not one route: each page's OWN rendered form, posted with the pair
    dropped and a token presented instead. A POST route added later joins PAGES and is
    walked here the day it is mounted."""
    agent = _client(gated, Authorization=f"Bearer {gated.token}")
    action, body = _form_for(agent, shape)
    body.pop("csrf_token")
    answered = agent.post(action, data=body)
    assert answered.status_code == (303 if shape in TOKEN_WRITES else 403), answered.text


def test_the_designed_404_page_is_unchanged(client: TestClient) -> None:
    """A refusal is an ``HTTPException`` on a page route like any other: pin that
    ``install_page_errors`` renders 404 exactly as it did, detail-free."""
    missing = client.get("/pmbok/9.9.9")
    assert missing.status_code == 404
    assert "Page not found" in missing.text and "9.9.9" not in missing.text
