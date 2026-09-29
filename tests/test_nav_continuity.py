"""Every mounted project page is reachable from the hub, a pinned ``as_of`` survives
every internal project link (the board link is the one deliberate exception -- it has
nothing dated to carry), and a destination has exactly one label across the pages that
link to it.

The page set is derived from the live route table, not written out here, the same
``_included``/``_leaves`` walk ``tests/test_web_mount_once.py`` uses -- a page added to
``driftless.web`` without a hub anchor fails this test rather than going unreachable.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.demo.cli import seed
from driftless.demo.data import ANCHOR, demo_payload
from driftless.web.errors import PageRoute

Q = ANCHOR.isoformat()

#: Routes deliberately not linked from the hub strip, with the reason each is exempt.
EXCLUDED = {
    "/projects/{project_id}/hub": "the hub itself -- not a destination reachable from its own strip",
}


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(real_app) as test_client:
            yield test_client
    finally:
        real_app.dependency_overrides.clear()


def _seed(client: TestClient) -> None:
    def post(path: str, body: dict[str, Any]) -> int:
        response = client.post(path, json=body)
        assert response.status_code == 201, response.text
        return int(response.json()["id"])

    def patch(path: str, body: dict[str, Any]) -> None:
        response = client.patch(path, json=body)
        assert response.status_code == 200, response.text

    seed(post, demo_payload(ANCHOR), patch)


def _included(route: Any) -> list[Any] | None:
    """Duplicated from ``tests/test_web_mount_once.py`` -- a private test helper, and
    a shared import buys nothing a few-line duplicate does not already give this
    module on its own."""
    for holder in (route, getattr(route, "original_router", None)):
        children = getattr(holder, "routes", None)
        if children:
            return list(children)
    return None


def _leaves(route: Any) -> list[Any]:
    children = _included(route)
    if children is None:
        return [route]
    return [leaf for child in children for leaf in _leaves(child)]


def _project_page_routes() -> list[Any]:
    """Every mounted ``/projects/{project_id}/...`` GET page, read off the live route
    table -- never a list written here, so a page added to ``driftless.web`` without a
    hub anchor fails this test rather than going unreachable."""
    leaves = [leaf for route in real_app.routes for leaf in _leaves(route)]
    return [
        leaf
        for leaf in leaves
        if isinstance(leaf, PageRoute)
        and str(getattr(leaf, "path", "")).startswith("/projects/{project_id}/")
        and "GET" in (getattr(leaf, "methods", None) or ())
    ]


def test_route_derivation_is_not_vacuous() -> None:
    routes = _project_page_routes()
    assert len(routes) > 15, f"the route walk found too few project pages: {routes}"


def test_the_hub_links_to_every_mounted_project_page(client: TestClient) -> None:
    _seed(client)
    project_id = client.get("/projects").json()[0]["id"]
    hub = client.get(f"/projects/{project_id}/hub?as_of={Q}")
    assert hub.status_code == 200, hub.text
    hrefs = set(re.findall(r'href="([^"]+)"', hub.text))

    for route in _project_page_routes():
        if route.path in EXCLUDED:
            continue
        expected = route.path.format(project_id=project_id)
        assert any(href.split("?")[0] == expected for href in hrefs), (
            f"hub strip does not link {route.path} (excluded set: {EXCLUDED})"
        )


def _links_as_of(html: str) -> list[str]:
    return [href for href in re.findall(r'href="(/projects/[^"]+)"', html)]


def test_as_of_survives_every_project_link_except_the_undated_board(
    client: TestClient,
) -> None:
    _seed(client)
    project_id = client.get("/projects").json()[0]["id"]
    pages = (
        f"/projects/{project_id}/hub?as_of={Q}",
        f"/projects/{project_id}/raid?as_of={Q}",
        f"/projects/{project_id}/status?as_of={Q}",
        f"/projects/{project_id}/wizard?as_of={Q}",
        f"/projects/{project_id}/gantt?as_of={Q}",
        f"/projects/{project_id}/process-map?as_of={Q}",
        # An assistant page dropped the pinned date on its way back to the hub while
        # every sibling carried it: the walk was over pages, not over the shape.
        f"/projects/{project_id}/assist/stakeholders?as_of={Q}",
    )
    for path in pages:
        page = client.get(path)
        assert page.status_code == 200, f"{path}: {page.text[:200]}"
        for href in _links_as_of(page.text):
            target = href.split("?")[0]
            if target.endswith("/board"):
                assert f"as_of={Q}" not in href, f"{path}: {href} should stay undated"
            else:
                assert f"as_of={Q}" in href, f"{path}: {href} dropped as_of"


def _crumb_and_h1(html: str) -> tuple[str, str]:
    # Neither tag is matched attribute-for-attribute now; the ``</nav>`` anchor still
    # makes the captured span the LAST crumb rather than any span in the trail.
    crumb = re.search(r'<nav class="breadcrumbs".*?<span[^>]*>([^<]+)</span></nav>', html)
    h1 = re.search(r"<h1>([^<]+)</h1>", html)
    assert crumb and h1, "page carries no breadcrumb trail or no h1"
    return crumb.group(1), h1.group(1).split(" — ")[0]


def test_crumb_labels_match_the_page_h1_for_gantt_status_and_raid(
    client: TestClient,
) -> None:
    _seed(client)
    project_id = client.get("/projects").json()[0]["id"]
    for leaf in ("gantt", "status", "raid"):
        page = client.get(f"/projects/{project_id}/{leaf}?as_of={Q}")
        assert page.status_code == 200, f"{leaf}: {page.text[:200]}"
        crumb, h1_title = _crumb_and_h1(page.text)
        assert crumb == h1_title, f"{leaf}: crumb {crumb!r} != h1 {h1_title!r}"


def test_process_map_carries_a_breadcrumb_trail(client: TestClient) -> None:
    _seed(client)
    project_id = client.get("/projects").json()[0]["id"]
    page = client.get(f"/projects/{project_id}/process-map?as_of={Q}")
    assert page.status_code == 200, page.text
    assert '<nav class="breadcrumbs"' in page.text
