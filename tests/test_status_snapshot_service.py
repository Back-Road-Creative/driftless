"""Both status-snapshot write paths go through one service, and neither owns the other.

The JSON route and the browser form have always filed the same row: the page handler
called the route function ``create_status_snapshot`` directly. That kept the two paths
honest but made ``driftless.web`` import ``driftless.api.app``, which imports
``driftless.web`` back to mount the pages — the cycle the mount-once flag and the
lifespan backstop exist to sequence around.

The write moves to :mod:`driftless.services.status_snapshots`, which neither side
imports the other to reach. The design property is unchanged and asserted here rather
than left to a docstring: **both routes still reach the same function.** A future edit
that gives the page its own copy of the write — a hand-typed percent, a skipped
schema — fails this file.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute

from driftless.api.app import app
from driftless.services.status_snapshots import create_status_snapshot

JSON_PATH = "/status-snapshots"
PAGE_PATH = "/projects/{project_id}/status"


def _leaves(route: Any) -> list[Any]:
    """``route``, or the routes an ``include_router`` hung under it — pages are nested."""
    for holder in (route, getattr(route, "original_router", None)):
        children = getattr(holder, "routes", None)
        if children:
            return [leaf for child in children for leaf in _leaves(child)]
    return [route]


def _reaches(endpoint: object, target: object) -> bool:
    """Whether ``endpoint`` IS ``target`` or calls it by bare name in its own body.

    Bare name deliberately: a ``module.create_status_snapshot(...)`` attribute call
    would read as the same write while being a different guarantee to verify.
    """
    if endpoint is target:
        return True
    try:
        source = inspect.getsource(endpoint)  # type: ignore[arg-type]
    except (OSError, TypeError):
        return False
    name = getattr(target, "__name__", None)
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
        for node in ast.walk(ast.parse(textwrap.dedent(source)))
    )


def _writing_routes() -> set[str]:
    return {
        leaf.path
        for route in app.routes
        for leaf in _leaves(route)
        if isinstance(leaf, APIRoute)
        and "POST" in (leaf.methods or set())
        and _reaches(leaf.endpoint, create_status_snapshot)
    }


def test_both_write_paths_reach_the_one_service() -> None:
    found = _writing_routes()
    assert JSON_PATH in found, f"the JSON route stopped using the service: {sorted(found)}"
    assert PAGE_PATH in found, f"the page grew its own write: {sorted(found)}"


def test_nothing_takes_the_write_off_the_app() -> None:
    """The point of the move — `driftless.web` must not reach into `driftless.api.app`."""
    src = Path(__file__).resolve().parents[1] / "driftless"
    offenders = [
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        if "create_status_snapshot"
        in {
            alias.name
            for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, ast.ImportFrom) and node.module == "driftless.api.app"
            for alias in node.names
        }
    ]
    assert not offenders, f"import it from driftless.services.status_snapshots: {offenders}"
