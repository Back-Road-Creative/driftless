"""The generic CRUD machinery is a module, not part of the app module.

``reads``, ``writes`` and ``creates`` -- and the seven helpers they lean on to window a
list, derive a filter vocabulary, refuse a stale write and reflect a delete's blocking
children -- are how roughly thirty resources get their routes. They are not the app: they
know nothing about which resources exist, and B1 already made them take the app they
register onto rather than closing over a global.

They lived in ``driftless.api.app`` only because everything did. This file pins the move:
they answer from :mod:`driftless.api.crud`, ``api/app.py`` no longer defines them, and the
routes they generate are still on the live table.
"""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi.routing import APIRoute

from driftless.api import crud
from driftless.api.app import app

APP_SOURCE = Path(__file__).resolve().parents[1] / "driftless" / "api" / "app.py"

MOVED = (
    "_stated_revision",
    "check_revision",  # re-exported: lives in driftless.services.concurrency now
    "_apply",
    "_delete",
    "_windowed",
    "_filter_vocabulary",
    "_query_parameter",
    "_filter_conditions",
    "reads",
    "writes",
    "creates",
)


def test_the_crud_machinery_answers_from_its_own_module() -> None:
    missing = [name for name in MOVED if not hasattr(crud, name)]
    assert not missing, f"expected in driftless.api.crud: {missing}"


def test_the_app_module_no_longer_defines_them() -> None:
    """A copy left behind is worse than no move: two definitions, one of them stale."""
    defined = {
        node.name
        for node in ast.walk(ast.parse(APP_SOURCE.read_text()))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert not defined & set(MOVED), f"still defined in api/app.py: {sorted(defined & set(MOVED))}"


def test_the_routes_they_generate_are_still_served() -> None:
    """Non-vacuous: the move is only correct if the generic surface survived it."""
    served = {
        (route.path, tuple(sorted(route.methods or ())))
        for route in app.routes
        if isinstance(route, APIRoute)
    }
    assert ("/projects", ("GET",)) in served, "the generic list route is gone"
    assert ("/projects/{row_id}", ("PATCH",)) in served, "the generic patch route is gone"
    assert ("/projects/{row_id}", ("DELETE",)) in served, "the generic delete route is gone"
