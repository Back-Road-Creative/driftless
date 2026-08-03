"""Empty, 404 and 500 states across the web surface.

A first-run install and the demo both land on a store with nothing in it, so a
surface with no rows is a product state, not an edge case: every list-shaped page
says what it is for and names the concrete next step (a command or a link), and
renders no headers-only table. The error shell is keyed on the *surface* —
``web.errors.PageRoute`` stamps the request scope — so a page 404s in HTML while
the JSON API keeps its JSON 404.
"""

import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.auth import sessions
from driftless.db import Base, new_engine, new_session_factory
from driftless.web.errors import PageRoute, install_page_errors

AS_OF = date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"
# What a browser sends and what a script sends, spelled out because the split between
# them is the only thing deciding an address that matched no route at all.
_BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
_JSON_404 = '{"detail":"Not Found"}'
_SECTION = re.compile(r'<section class="empty-state"[^>]*>(.*?)</section>', re.S)
_EMPTY_ID = re.compile(r'<section class="empty-state" id="([\w-]+)"')
_ROLE_IMG = re.compile(r'<svg\b[^>]*\brole="img"[^>]*>(.*?)</svg>', re.S)
_CSRF_DETAIL = "The form's CSRF token is missing or stale."  # never reaches a page
# The JSON API's 422, captured off master before ``errors.py`` grew a
# RequestValidationError handler: the API surface must not move a single byte.
_API_422 = (
    '{"detail":[{"type":"int_parsing","loc":["path","row_id"],"msg":"Input should be a valid '
    'integer, unable to parse string as an integer","input":"abc"}]}'
)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    # https, as production serves: an http jar drops the ``Secure`` CSRF cookie, so
    # ``csrf.ensure`` would remint per render and byte-identity below could not hold.
    # The cookie-LESS reading of the same property is pinned separately, in
    # test_web_csrf.test_the_token_is_the_only_thing_a_cookieless_refetch_changes.
    with TestClient(real_app, base_url="https://testserver") as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def _skeletons(db: Session) -> tuple[str, ...]:
    """A portfolio, program, department and project that are all real rows with
    nothing underneath — every "no children" surface in one store, the chart-shaped
    ones included: a project with no snapshot and no baseline draws neither of the
    weekly-status charts, and each empty slot owes the same next step a list does."""
    business = m.Business(name="BRC")
    bare = m.Portfolio(name="Bare Brands", business=business)
    portfolio = m.Portfolio(name="Content Brands", business=business)
    program = m.Program(name="Video", portfolio=portfolio)
    dept = m.Department(business=business, name="Delivery")
    project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    db.add_all([bare, program, dept, project])
    db.commit()
    return (
        f"/portfolios/{bare.id}/rollup",
        f"/programs/{program.id}/rollup",
        f"/org/departments/{dept.id}",
        f"/projects/{project.id}/hub",
        f"/projects/{project.id}/status",
    )


def _assert_designed(client: TestClient, path: str) -> None:
    page = client.get(f"{path}{Q}")
    assert page.status_code == 200, page.text
    bodies = _SECTION.findall(page.text)
    assert bodies, f"{path} renders no designed empty state"
    for body in bodies:
        assert "<code" in body or "<a " in body, f"{path}'s empty state names no next step"
    assert "<table" not in page.text, f"{path} still renders a headers-only table skeleton"


def _project_with_a_trend(db: Session) -> str:
    """A weekly-status page with points to draw — an empty chart hides nothing."""
    business = m.Business(name="BRC")
    portfolio = m.Portfolio(name="Content Brands", business=business)
    project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    db.add(project)
    db.flush()
    db.add_all(
        m.StatusSnapshot(
            project_id=project.id, taken_on=taken_on, percent_complete=percent, rag_status=rag
        )
        for taken_on, percent, rag in ((date(2026, 1, 5), 10, "red"), (AS_OF, 85, "green"))
    )
    db.commit()
    return f"/projects/{project.id}/status"


def test_a_chart_calling_itself_one_image_hides_nothing_inside_it(
    client: TestClient, db: Session
) -> None:
    """``role="img"`` makes an SVG a single node and prunes its whole subtree, so a
    ``<title>`` or an ``<a>`` under one reaches nobody reading the accessibility tree
    while looking, in the source, like the text alternative it is not. Both weekly-status
    charts print their data as a table twin beside them, so a per-point tooltip is a
    duplicate a mouse can reach and a screen reader cannot. Walked rather than asserted
    once, so a new hover string cannot be added back to either chart quietly."""
    page = client.get(f"{_project_with_a_trend(db)}{Q}")
    assert page.status_code == 200, page.text
    charts = _ROLE_IMG.findall(page.text)
    assert charts, "the weekly-status page draws no role=img chart to check"
    for body in charts:
        hidden = [tag for tag in ("<title", "<a ") if tag in body]
        assert not hidden, (
            f"a role=img chart on the weekly-status page carries {hidden} inside it: "
            "the role prunes that subtree, so the markup is unreachable to the "
            "accessibility tree — delete it, or the role is the wrong one"
        )


def test_each_weekly_status_chart_slot_owns_its_own_empty_state(
    client: TestClient, db: Session
) -> None:
    """The two charts empty INDEPENDENTLY and are filled by different actions — a
    snapshot from the form below them, a baseline with lines and dated spend — so one
    shared line cannot serve both, and each names its own next step.

    The trend's fallback was a bare italic sentence written outside ``_empty.html``,
    which ``_assert_designed`` could not even see: the walk reads sections carrying
    ``class="empty-state"`` and an italic ``<p>`` carries none. Asserting the exact
    pair of ids is what makes that walk reach both slots — a slot that drops back out
    of the shared state fails here rather than going quietly unchecked.
    """
    status = next(path for path in _skeletons(db) if path.endswith("/status"))
    page = client.get(f"{status}{Q}")
    assert page.status_code == 200, page.text
    assert set(_EMPTY_ID.findall(page.text)) == {"trend-empty", "evm-empty"}, (
        "each weekly-status chart with nothing to draw owes the shared empty state "
        "and a next step of its own, never an italic line naming neither"
    )


def test_the_empty_store_surfaces_say_what_they_are_for(client: TestClient) -> None:
    for path in ("/", "/threats", "/org/departments"):
        _assert_designed(client, path)


def test_a_node_with_no_children_says_what_to_do_next(client: TestClient, db: Session) -> None:
    for path in _skeletons(db):
        _assert_designed(client, path)


def test_an_unknown_id_on_a_page_path_renders_the_html_404_shell(client: TestClient) -> None:
    for path in ("/org/departments/9", "/projects/9/hub", "/portfolios/9/rollup", "/pmbok/9.9"):
        page = client.get(path)
        assert page.status_code == 404, page.text
        assert page.headers["content-type"].startswith("text/html"), path
        assert 'href="/threats"' in page.text, f"{path} lost the shared shell"


def test_the_json_api_keeps_its_json_404_exactly(client: TestClient) -> None:
    got = client.get("/departments/999")
    assert got.status_code == 404
    assert got.headers["content-type"].startswith("application/json")
    assert got.json() == {"detail": "Department 999 not found"}


def test_a_stale_form_token_renders_the_designed_expired_form_page(client: TestClient) -> None:
    """A form left open too long is the commonest 403 a browser can trigger, and the
    user can fix it: say it expired and say to reload. Not "something went wrong",
    and never the exception's own detail."""
    refused = client.post(
        "/sign-off",
        data={
            "subject_kind": "deliverable",
            "subject_ref": "charter",
            "decision": "approved",
            "csrf_token": "stale",
        },
        follow_redirects=False,
    )
    assert refused.status_code == 403, refused.text
    assert refused.headers["content-type"].startswith("text/html")
    assert 'href="/threats"' in refused.text, "the 403 lost the shared shell"
    assert "expired" in refused.text and "Reload the page" in refused.text
    for leak in (_CSRF_DETAIL, "CSRF", "stale", "could not be rendered"):
        assert leak not in refused.text, f"the 403 page leaks {leak!r}"


def test_a_malformed_page_address_renders_the_html_404_shell(client: TestClient) -> None:
    """``/projects/abc/hub`` fails path validation, which is not an HTTPException —
    on master the browser got a raw JSON validation dump."""
    page = client.get("/projects/abc/hub")
    assert page.status_code == 404, page.text
    assert page.headers["content-type"].startswith("text/html")
    assert "Page not found" in page.text and 'href="/threats"' in page.text
    for leak in ("int_parsing", "abc", "detail"):
        assert leak not in page.text, f"the malformed-address page leaks {leak!r}"


def test_an_address_matching_no_route_renders_the_html_404_shell(client: TestClient) -> None:
    """The address bar's own 404 — a typed address that matched NOTHING.

    Both existing readings of "this is a page" can only speak for a route that exists:
    ``PAGE_SCOPE_KEY`` is stamped by a page route's handler, and ``_page_patterns`` is
    compiled from the page routes themselves. A request routed nowhere has neither, so
    ``/projects/1/boardz`` — one letter off a real page — was answered with FastAPI's
    JSON default at an address a person had typed.
    """
    client.cookies.set(sessions.COOKIE, "browser-session")  # signed in, as a reader would be
    for path in ("/projects/1/boardz", "/no-such-page", "/projects/1/hub/extra"):
        page = client.get(path, headers=_BROWSER)
        assert page.status_code == 404, page.text
        assert page.headers["content-type"].startswith("text/html"), path
        assert "Page not found" in page.text, path
        assert 'href="/threats"' in page.text, f"{path} lost the shared shell"
        assert "detail" not in page.text, f"{path} leaks the JSON body"


def test_a_client_that_did_not_ask_for_html_keeps_the_json_404(client: TestClient) -> None:
    """The discriminator stated as its negative, and the reason it is the ``Accept``
    header only here: a request that matched no route has no surface to be read off it.

    Curl sends no ``Accept`` at all, httpx sends ``*/*``; neither asked for a page, so
    both keep the body a script already parses — at a page-shaped address as much as an
    API-shaped one, since neither of them named a route.
    """
    client.headers.pop("accept", None)  # curl's shape: the header is absent, not ``*/*``
    for headers in ({}, {"Accept": "*/*"}, {"Accept": "application/json"}):
        for path in ("/projects/1/boardz", "/no-such-api-route"):
            got = client.get(path, headers=headers)
            assert got.status_code == 404, (path, headers)
            assert got.headers["content-type"].startswith("application/json"), (path, headers)
            assert got.text == _JSON_404, (path, headers)


def test_a_page_route_that_refuses_the_method_renders_the_shell(client: TestClient) -> None:
    """The same defect one status along: 405 is raised before the endpoint runs, so no
    stamp is on the scope — but the request DID match a page route, and that is read
    straight off the scope, so no ``Accept`` is consulted and the client here sends
    ``*/*``. The API's own 405 does not move.
    """
    page = client.post("/threats")
    assert page.status_code == 405, page.text
    assert page.headers["content-type"].startswith("text/html")
    assert 'href="/threats"' in page.text, "the 405 lost the shared shell"
    assert "does not accept" in page.text, "the 405 says nothing a reader can act on"
    assert "detail" not in page.text and "logged" not in page.text
    api = client.patch("/departments")
    assert api.status_code == 405
    assert api.text == '{"detail":"Method Not Allowed"}'


def test_the_json_api_keeps_its_own_403_and_422_bodies_byte_for_byte(client: TestClient) -> None:
    """No page stamp, so both refusals stay FastAPI's — the 422 pinned against master."""
    app = FastAPI()

    @app.get("/api-403")
    def forbidden() -> None:
        raise HTTPException(403, "the pair did not match")

    install_page_errors(app)
    with TestClient(app) as harness:
        refused = harness.get("/api-403")
    assert refused.status_code == 403
    assert refused.text == '{"detail":"the pair did not match"}'
    malformed = client.get("/departments/abc")
    assert malformed.status_code == 422, malformed.text
    assert malformed.headers["content-type"].startswith("application/json")
    assert malformed.text == _API_422


def test_a_page_500_shows_nothing_about_the_exception_and_the_api_500_is_unchanged() -> None:
    """The page renders the shell with no traceback, query or SQL; the API answers
    Starlette's own plain 500; and neither swallows the error, since
    ``ServerErrorMiddleware`` re-raises after the handler returns."""
    app = FastAPI()
    pages = APIRouter(route_class=PageRoute)

    @pages.get("/boom-page", response_class=HTMLResponse)
    @app.get("/boom-api")
    def boom() -> None:
        raise RuntimeError("SELECT secret FROM ledger")

    app.include_router(pages)
    install_page_errors(app)
    with TestClient(app, raise_server_exceptions=False) as client:
        page, api = client.get("/boom-page"), client.get("/boom-api")
    assert page.status_code == 500 and page.headers["content-type"].startswith("text/html")
    for leak in ("secret", "SELECT", "Traceback", "RuntimeError"):
        assert leak not in page.text, f"the 500 page leaks {leak!r}"
    assert (api.status_code, api.text) == (500, "Internal Server Error")
    with TestClient(app) as strict, pytest.raises(RuntimeError):
        strict.get("/boom-page")


def test_a_pinned_as_of_stays_byte_identical(client: TestClient, db: Session) -> None:
    for path in ("/", "/threats", "/org/departments", *_skeletons(db)):
        assert client.get(f"{path}{Q}").text == client.get(f"{path}{Q}").text, path
