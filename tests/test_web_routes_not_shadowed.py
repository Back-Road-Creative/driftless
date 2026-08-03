"""No web page may share a GET path with the JSON CRUD API.

``driftless.api.app`` registers every generic CRUD route at import, then
``_mount_web`` includes the page routers — and FastAPI matches in registration
order. A page whose path equals a CRUD path is therefore *shadowed*: the
request is answered with JSON and the template never renders, while every
router-level test of that page (assembled on a bare ``FastAPI()``) keeps
passing. That is exactly how the department pages shipped unreachable.

So this walks the real app once and asserts the two sets of GET paths are
disjoint. It is an upstream gate on the whole class — a new page colliding
with a CRUD path fails here instead of shipping dead.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from starlette.routing import BaseRoute

from driftless.api.app import app

_PARAM = re.compile(r"\{[^}]*\}")


def _shape(path: str) -> str:
    """``/departments/{row_id}`` and ``/departments/{department_id}`` are one
    and the same path to the router, so compare parameter *shapes*."""
    return _PARAM.sub("{}", path)


def _included(route: BaseRoute) -> list[BaseRoute] | None:
    """The routes an ``include_router`` call contributed, or ``None`` when the
    route was registered directly on the app.

    FastAPI nests an included router under a wrapper route rather than copying
    its routes onto the app; depending on the version the children hang off
    ``routes`` or off ``original_router.routes``. A ``Mount`` (the static-files
    one) exposes neither and counts as a direct route — it carries no
    ``methods`` so it never reaches either set.
    """
    for holder in (route, getattr(route, "original_router", None)):
        children = getattr(holder, "routes", None)
        if children:
            return list(children)
    return None


def _leaves(route: BaseRoute) -> list[BaseRoute]:
    children = _included(route)
    if children is None:
        return [route]
    return [leaf for child in children for leaf in _leaves(child)]


def _get_paths(routes: Iterable[BaseRoute]) -> set[str]:
    return {
        _shape(str(getattr(route, "path", "")))
        for route in routes
        if "GET" in (getattr(route, "methods", None) or ())
    }


def _api_and_web_paths() -> tuple[set[str], set[str]]:
    """(paths registered directly by the API module, paths the web routers add)."""
    direct: list[BaseRoute] = []
    included: list[BaseRoute] = []
    for route in app.routes:
        children = _included(route)
        if children is None:
            direct.append(route)
        else:
            included.extend(leaf for child in children for leaf in _leaves(child))
    return _get_paths(direct), _get_paths(included)


def test_the_walk_reaches_the_pages_nested_inside_the_included_routers() -> None:
    """Guard against a vacuous pass: reading only the app's top level collects
    no page paths at all, and disjointness would then hold for free."""
    api, web = _api_and_web_paths()
    assert {"/", "/pmbok", "/process-map"} <= web, sorted(web)
    assert {"/departments", "/departments/{}"} <= api, sorted(api)


def test_no_web_page_is_shadowed_by_a_crud_route() -> None:
    api, web = _api_and_web_paths()
    collisions = sorted(api & web)
    assert not collisions, (
        f"{collisions} are registered as JSON CRUD before the page router is included, so "
        "FastAPI answers with JSON and the page never renders. Give the page its own path "
        "(the convention here: /org/departments, /projects/{id}/hub, /portfolios/{id}/rollup)."
    )
