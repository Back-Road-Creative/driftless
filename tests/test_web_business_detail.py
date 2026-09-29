"""The business detail surface is its own controller, not part of the ITTO page module.

Fifth slice of the incremental ``web/pages.py`` carve, same contract as the four before
it. ``tests/test_web_business.py`` stays the behavioural suite — it drives the page
through the real assembled app (``test_web_pages.client``), so it follows the route to
its new module without an edit, which is the point of mounting controllers in
``api/assembly.py`` rather than nesting them.

Neither perf fixture requests ``/business/{id}``: ``test_perf_commercial_volume.py``
prices ``/``, ``/process-map`` and ``/threats``, and ``test_perf_n1.py`` counts
process-map, hub and wizard. (Both files mention ``business_process_cells``, which this
page calls — but they reach it through the business MAP, a different route in a module
this slice does not touch.)
"""

from __future__ import annotations

from datetime import date

from starlette.routing import Route

from driftless.api.app import app
from driftless.api.openapi import page_route_paths
from driftless.web.business_detail import create_business_detail_router

AS_OF = date(2026, 3, 1)
DETAIL_PATH = "/business/{business_id}"


def _paths(routes: list[object]) -> set[str]:
    return {route.path for route in routes if isinstance(route, Route)}


def test_the_detail_page_has_a_controller_of_its_own() -> None:
    assert _paths(create_business_detail_router(AS_OF).routes) == {DETAIL_PATH}


def test_the_live_app_still_serves_the_detail_page() -> None:
    assert DETAIL_PATH in page_route_paths(app)
