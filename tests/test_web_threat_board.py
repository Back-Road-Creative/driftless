"""The threat board is its own controller, not part of the ITTO page module.

Second slice of the incremental ``web/pages.py`` carve, and the same contract the
PMBOK slice set (``tests/test_web_pmbok_reference.py``): the route leaves ``pages.py``,
the live app still serves it, and nothing a reader can see changes.

``THREATS_PER_PAGE`` travels WITH the route rather than staying behind. It is read by
name inside the handler, so a copy left in ``pages.py`` would be the one every caller
patched and none the board consulted — a page-size test that passes while proving
nothing. Both existing callers move with it, and this file pins the constant's new home
so the next mover finds it rather than re-deriving it.
"""

from __future__ import annotations

from datetime import date

from starlette.routing import Route

from driftless.api.app import app
from driftless.api.openapi import page_route_paths
from driftless.web.threat_board import THREATS_PER_PAGE, create_threat_board_router

AS_OF = date(2026, 3, 1)
BOARD_PATH = "/threats"


def _paths(routes: list[object]) -> set[str]:
    return {route.path for route in routes if isinstance(route, Route)}


def test_the_board_has_a_controller_of_its_own() -> None:
    assert _paths(create_threat_board_router(AS_OF).routes) == {BOARD_PATH}


def test_the_live_app_still_serves_the_board() -> None:
    assert BOARD_PATH in page_route_paths(app)


def test_the_page_size_is_still_a_positive_int() -> None:
    """The docs suite asserts this exact number appears in the user guide."""
    assert isinstance(THREATS_PER_PAGE, int) and THREATS_PER_PAGE > 0
