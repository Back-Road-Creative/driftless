"""The project process map is its own controller, not part of the ITTO page module.

Third slice of the incremental ``web/pages.py`` carve, same contract as the two before
it (``test_web_pmbok_reference.py``, ``test_web_threat_board.py``): the route leaves
``pages.py``, the live app still serves it, and nothing a reader can see changes.

``/sign-off`` stays behind and still redirects a process decision to
``/projects/{id}/process-map``. That target is built from a validated integer id into a
path literal — not an import — so the split does not touch it, and this file pins the
redirect so the two modules can be read apart.
"""

from __future__ import annotations

from datetime import date

from starlette.routing import Route

from driftless.api.app import app
from driftless.api.openapi import page_route_paths
from driftless.web import sign_off
from driftless.web.process_map import create_process_map_router

AS_OF = date(2026, 3, 1)
MAP_PATH = "/projects/{project_id}/process-map"


def _paths(routes: list[object]) -> set[str]:
    return {route.path for route in routes if isinstance(route, Route)}


def test_the_map_has_a_controller_of_its_own() -> None:
    assert _paths(create_process_map_router(AS_OF).routes) == {MAP_PATH}


def test_the_live_app_still_serves_the_map() -> None:
    assert MAP_PATH in page_route_paths(app)


def test_a_process_sign_off_still_redirects_to_the_map() -> None:
    """The one thing that crosses the split: sign-off's per-project redirect target.

    Built from the validated id rather than an allowlist entry, so it cannot be an
    open redirect — and it must keep naming the path the map now serves from its new
    module.
    """
    assert sign_off._sign_off_redirect("process", 7, None) == "/projects/7/process-map"
