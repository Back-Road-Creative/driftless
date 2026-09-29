"""The wizard routes are their own controller — the last read/write pair to leave pages.py.

Seventh slice of the carve, and the first that moves a WRITE route. ``wizard_apply`` is
the one form POST with no JSON twin (``/sign-offs`` and ``/status-snapshots`` have one),
so it is also the one write an agent drives with a token — which is why it, alone among
the page routes, goes through ``credentials.require_pair_unless_bearer`` rather than
``csrf.require``. That rule moved to its own module in #247 precisely so this route could
follow without dragging ``pages.py`` behind it.

Its form model moved in #248. This is the third and last piece.
"""

from __future__ import annotations

from datetime import date

from starlette.routing import Route

from driftless.api.app import app
from driftless.api.openapi import page_route_paths
from driftless.web.wizard_pages import create_wizard_router

AS_OF = date(2026, 3, 1)
WIZARD_PATHS = {"/projects/{project_id}/wizard", "/projects/{project_id}/wizard/apply"}


def _paths(routes: list[object]) -> set[str]:
    return {route.path for route in routes if isinstance(route, Route)}


def test_the_wizard_has_a_controller_of_its_own() -> None:
    assert _paths(create_wizard_router(AS_OF).routes) == WIZARD_PATHS


def test_the_live_app_still_serves_both() -> None:
    assert WIZARD_PATHS <= page_route_paths(app)
