"""Nothing is more than two clicks from the front door — the worst threat least of all.

The promise: from ``/``, a reader reaches the worst threat's detail — the finding
itself, the recommended actions its assessment attached, and the control that acts
on it — within :data:`CLICK_BUDGET` clicks; and every page the app mounts sits
inside that same budget, so a surface added later cannot quietly lengthen the walk.

Both halves are *walked*, never listed:

* The link graph is crawled by following the ``href``s the server actually
  rendered. A test that built the target URL itself would prove routing, not
  reachability — it would stay green with every link to that page deleted.
* The route table is discovered by recursing the app's routes the way
  ``driftless.api.secure._leaves`` does (FastAPI hangs an included router's
  children off a wrapper, so a naive walk of ``app.routes`` finds no page at all),
  so a page added next year is covered without anyone editing this file.

Today the answer is one click, not two: ``base.html``'s "Threats" nav link reaches
``/threats``, whose top-ranked card carries the finding, its PMBOK actions and the
sign-off form. The dashboard's own attention rail shows the same finding at zero
clicks, but not the assessment's actions, so the board is the detail surface. The
budget therefore has a click of slack — and it can no longer be spent silently.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.routing import BaseRoute

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.assess import engine as assess
from driftless.demo.cli import seed
from driftless.demo.data import ANCHOR, demo_payload
from driftless.web import pages
from driftless.web.errors import PageRoute

#: The product's bound: the worst thing wrong is at most this many clicks from ``/``.
CLICK_BUDGET = 2
AS_OF = ANCHOR.isoformat()
_HREF = re.compile(r'href="([^"]+)"')


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """The real app over the throwaway store — the wiring every page test uses."""
    real_app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(real_app) as test_client:
            yield test_client
    finally:
        real_app.dependency_overrides.clear()


def _seed(client: TestClient) -> None:
    """The shipped demo store, written through the validated API — never raw rows."""

    def post(path: str, body: dict[str, Any]) -> int:
        response = client.post(path, json=body)
        assert response.status_code == 201, response.text
        return int(response.json()["id"])

    def patch(path: str, body: dict[str, Any]) -> None:
        response = client.patch(path, json=body)
        assert response.status_code == 200, response.text

    seed(post, demo_payload(ANCHOR), patch)


def _leaves(route: BaseRoute) -> list[BaseRoute]:
    """``route`` itself, or the routes an ``include_router`` call nested under it."""
    for holder in (route, getattr(route, "original_router", None)):
        children = getattr(holder, "routes", None)
        if children:
            return [leaf for child in children for leaf in _leaves(child)]
    return [route]


def _page_routes() -> list[PageRoute]:
    """Every GET page route the app mounts, discovered rather than written down."""
    return [
        leaf
        for route in real_app.routes
        for leaf in _leaves(route)
        if isinstance(leaf, PageRoute) and "GET" in (leaf.methods or ())
    ]


def _crawl(client: TestClient) -> dict[str, tuple[int, str]]:
    """Every page within :data:`CLICK_BUDGET` clicks of ``/``: path -> (clicks, html).

    Follows only hrefs the server rendered, and only those matching a discovered page
    route — a static asset or a JSON endpoint is not a page. Every fetch pins ``as_of``
    so the walk is deterministic; the query a link carried is dropped, which at worst
    revisits a page the graph already holds.
    """
    routes = _page_routes()
    reached: dict[str, tuple[int, str]] = {}
    frontier = ["/"]
    for clicks in range(CLICK_BUDGET + 1):
        following: list[str] = []
        for path in frontier:
            page = client.get(path, params={"as_of": AS_OF})
            assert page.status_code == 200, f"{path}: {page.text[:200]}"
            # Entities decoded once here, so a finding containing & or a quote is
            # matched as the engine wrote it rather than as Jinja escaped it.
            reached[path] = (clicks, html.unescape(page.text))
            if clicks == CLICK_BUDGET:
                continue
            for href in _HREF.findall(reached[path][1]):
                target = href.split("?")[0].split("#")[0]
                if target in reached or target in following:
                    continue
                if any(route.path_regex.fullmatch(target) for route in routes):
                    following.append(target)
        frontier = following
    return reached


def test_the_walk_finds_the_pages_and_follows_the_links_between_them(
    client: TestClient,
) -> None:
    """Guard against a vacuous pass: a walk that discovered no route, or followed no
    link, would satisfy both bounds below for free."""
    _seed(client)
    routes = _page_routes()
    assert len(routes) >= 15, f"the route walk lost the pages nested in the routers: {routes}"
    reached = _crawl(client)
    assert reached["/"][0] == 0, "the walk starts at the front door"
    depths = {clicks for clicks, _ in reached.values()}
    assert depths == set(range(CLICK_BUDGET + 1)), (
        f"the walk never got {CLICK_BUDGET} deep: {depths}"
    )


def test_the_worst_threat_and_its_actions_are_inside_the_click_budget(
    client: TestClient, db: Session
) -> None:
    """The worst thing wrong with the portfolio, and what to do about it, within budget.

    "Worst" is the engine's own answer (``top_threats``' first, which is the board's
    first card), never a threat this test picked; the page it is found on is whatever
    the crawl reached by following links, never a URL assembled here.
    """
    _seed(client)
    worst = assess.top_threats(db, ANCHOR)[0]
    card = pages.threat_cards(db, ANCHOR)[0]
    assert card["id"] == worst.id, "the board's first card is no longer the worst threat"
    detail = [worst.description, 'action="/sign-off"', f'value="{worst.id}"']
    detail += [str(action["label"]) for action in card["actions"]]
    assert len(detail) > 3, "the worst threat carries no recommended action to be reachable"

    found = {
        path: clicks
        for path, (clicks, body) in _crawl(client).items()
        if all(p in body for p in detail)
    }

    assert found, (
        f"no page within {CLICK_BUDGET} clicks of / shows threat {worst.id}, the actions "
        f"its assessment attached and a control that acts on it — the worst thing wrong "
        f"with the portfolio is now further from the front door than the product promises"
    )


def test_every_page_the_app_mounts_is_inside_the_click_budget(client: TestClient) -> None:
    """No mounted page is further than the budget, so a new one cannot lengthen the walk.

    Discovered, not listed: a page added later is checked here without anyone
    remembering to, which is the only version of this guard that keeps working.
    """
    _seed(client)
    reached = _crawl(client)
    orphans = sorted(
        route.path
        for route in _page_routes()
        if not any(route.path_regex.fullmatch(path) for path in reached)
    )
    assert not orphans, (
        f"{orphans} are mounted but no chain of {CLICK_BUDGET} links from / reaches them: "
        "link the page from the dashboard, or from a page the dashboard links."
    )
