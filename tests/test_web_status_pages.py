"""The weekly-status edit flow is its own controller, and pages.py is now a husk.

Tenth and last slice of the carve. ``status_form`` and ``status_submit`` are the
read/write pair behind the weekly RAG snapshot, and the only routes left in ``web/pages.py``
— the module that started as the whole ITTO web surface.

Both verbs are asserted, not just the path: a GET page and its POST submit are distinct
route objects on one path, and moving only the one you were looking at leaves the other
405-ing. ``web/pages.py`` is deleted in this change, so this file is where its absence is pinned.
"""

from __future__ import annotations

import importlib
from datetime import date

import pytest

from starlette.routing import Route

from driftless.api.app import app
from driftless.api.openapi import page_route_paths
from driftless.web import status

AS_OF = date(2026, 3, 1)
STATUS_PATH = "/projects/{project_id}/status"
STATUS_INPUTS_PATH = "/projects/{project_id}/status/inputs"


def _paths(routes: list[object]) -> set[str]:
    return {route.path for route in routes if isinstance(route, Route)}


def test_the_status_pair_has_a_controller_of_its_own() -> None:
    routes = [r for r in status.create_status_router(AS_OF).routes if isinstance(r, Route)]
    assert {r.path for r in routes} == {STATUS_PATH, STATUS_INPUTS_PATH}
    status_routes = [r for r in routes if r.path == STATUS_PATH]
    assert {"GET", "POST"} <= {verb for r in status_routes for verb in (r.methods or ())}


def test_the_itto_page_module_is_gone() -> None:
    """The husk is deleted. Asserted, not assumed: re-creating it would silently give
    a route two possible homes again, which is the whole condition the carve removed."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("driftless.web.pages")


def test_the_live_app_still_serves_it() -> None:
    assert STATUS_PATH in page_route_paths(app)
