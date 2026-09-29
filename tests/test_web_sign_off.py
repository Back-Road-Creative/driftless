"""Sign-off is its own controller, and its redirect table outlived the module it sat in.

Eighth slice of the carve. ``POST /sign-off`` is posted from two surfaces — the threat
board and the home rail — and both now live in modules of their own, so the redirect
allowlist it consults was the last thing tying it to ``web/pages.py``.

The redirect is the part worth pinning. It is derived from the SUBJECT, never from the
posted target: a process decision goes back to the per-project map (a path built from an
already-validated integer id, so it cannot be anything but ours), and everything else
falls back to a two-entry allowlist. A posted value outside that set must not survive —
that is what keeps this route from being an open redirect.
"""

from __future__ import annotations

from datetime import date

from starlette.routing import Route

from driftless.api.app import app
from driftless.api.openapi import page_route_paths
from driftless.web import sign_off

AS_OF = date(2026, 3, 1)
SIGN_OFF_PATH = "/sign-off"


def _paths(routes: list[object]) -> set[str]:
    return {route.path for route in routes if isinstance(route, Route)}


def test_sign_off_has_a_controller_of_its_own() -> None:
    assert _paths(sign_off.create_sign_off_router(AS_OF).routes) == {SIGN_OFF_PATH}


def test_the_live_app_still_serves_it() -> None:
    assert SIGN_OFF_PATH in page_route_paths(app)


def test_a_process_decision_returns_to_its_own_project_map() -> None:
    """Built from the validated id, so no allowlist entry could ever hold it."""
    assert sign_off._sign_off_redirect("process", 7, None) == "/projects/7/process-map"


def test_an_off_list_target_cannot_survive_the_round_trip() -> None:
    """The open-redirect guard: anything not on the allowlist falls back to /threats."""
    assert sign_off._sign_off_redirect("threat", None, "https://evil.example/x") == "/threats"
    assert sign_off._sign_off_redirect("threat", None, "/") == "/"
