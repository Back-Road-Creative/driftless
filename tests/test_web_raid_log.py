"""The RAID log is its own controller, not part of the ITTO page module.

Fourth slice of the incremental ``web/pages.py`` carve, same contract as the three
before it: the route leaves ``pages.py``, the live app still serves it, and nothing a
reader can see changes. ``tests/test_web_raid.py`` remains the behavioural suite — what
the page renders is its question, not this file's.

Unlike ``/threats`` and ``/process-map``, neither perf fixture builds an app that
exercises this route (``MEASURED`` in ``test_perf_commercial_volume.py`` names ``/``,
``/process-map`` and ``/threats``; ``test_perf_n1.py`` counts process-map, hub and
wizard), so nothing there needed the new router. Checked, not assumed — the previous two
slices both turned on exactly that question.
"""

from __future__ import annotations

from datetime import date

from starlette.routing import Route

from driftless.api.app import app
from driftless.api.openapi import page_route_paths
from driftless.web.raid_log import create_raid_log_router

AS_OF = date(2026, 3, 1)
RAID_PATH = "/projects/{project_id}/raid"


def _paths(routes: list[object]) -> set[str]:
    return {route.path for route in routes if isinstance(route, Route)}


def test_the_raid_log_has_a_controller_of_its_own() -> None:
    assert _paths(create_raid_log_router(AS_OF).routes) == {RAID_PATH}


def test_the_live_app_still_serves_the_raid_log() -> None:
    assert RAID_PATH in page_route_paths(app)
