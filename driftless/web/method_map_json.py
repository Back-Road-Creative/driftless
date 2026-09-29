"""The method graph as read-only JSON: ``GET /map/graph.json``.

This is the one place the decision recorded in ``docs/architecture.md`` -- "the
JSON API does not expose the technique registry" -- stops being true: the
whole method graph, techniques included, is now reachable as JSON, read-only,
with no store and no auth beyond what any other reference page needs, because
:data:`driftless.pmbok.graph.GRAPH` is built once at import and is pure: a
fresh ``_build()`` always equals it, so nothing here takes an as-of.

**Registered directly on ``app``**, the same way ``driftless.api.app``'s own
``_register_routes`` adds ``/health``, ``/calendar.ics`` and
``/search/results`` -- ``app.add_api_route``, not ``app.include_router`` --
rather than mounted through :func:`driftless.api.assembly.mount_web`. That is
not a style choice: ``tests/test_web_a11y.py``, ``tests/test_web_csrf.py`` and
``tests/test_web_responsive.py`` each walk "every page the app registers" by
asking which GET routes an *included* router contributed
(``driftless.web.errors.PageRoute`` plays no part in that walk), because that
is exactly how a page mounted through ``mount_web`` is told apart from a CRUD
endpoint added straight to ``app`` -- and a JSON response has no viewport meta,
no sign-out form and no CSRF pair for those walks to find. Registering this
route directly keeps it out of that "page" set the same way ``/health`` and
``/search/results`` already are, and in the API's own OpenAPI schema the same
way they are too.

``GRAPH.to_dict()`` already gives node/edge tuples as plain dicts; the
addition here is a top-level ``source_version``, read from
:data:`driftless.pmbok.definitions.PMBOK_SOURCE_VERSION` rather than
restated, so the two can never drift apart, and per node the same ``x``/``y``
:data:`driftless.pmbok.graph_layout.LAYOUT` places the SVG node at, plus
``group``/``area`` (process nodes), ``family`` (technique and artifact
nodes) and ``href`` -- the node's own page, the exact link
``method_map.node_href`` gives the SVG node -- so a reader of this route alone
can redraw the map without also fetching ``/map``.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from driftless.pmbok.artifact_definitions import ARTIFACTS
from driftless.pmbok.definitions import PMBOK_SOURCE_VERSION, TECHNIQUES
from driftless.pmbok.graph import GRAPH
from driftless.pmbok.graph_layout import LAYOUT
from driftless.pmbok.process_definitions import PROCESS_DEFINITIONS
from driftless.web.method_map import node_href


def _node_extras(node_id: str, kind: str, key: str) -> dict[str, Any]:
    """The redraw fields one node adds beyond ``GRAPH.to_dict()``'s own
    ``id``/``kind``/``label``: position plus whichever of
    group/area/family apply to this node's kind, the rest ``None``."""
    x, y = LAYOUT.positions[node_id]
    group = area = family = None
    if kind == "process":
        process = PROCESS_DEFINITIONS[key].process
        group, area = process.group.value, process.area.value
    elif kind == "technique":
        family = TECHNIQUES[key].family.value
    elif kind == "artifact":
        family = ARTIFACTS[key].family.value
    return {
        "x": x,
        "y": y,
        "group": group,
        "area": area,
        "family": family,
        "href": node_href(node_id),
    }


def graph_payload() -> dict[str, Any]:
    """The frozen graph as one JSON-serialisable dict, version first, every
    node widened with its redraw fields (see the module docstring)."""
    payload: dict[str, Any] = {"source_version": PMBOK_SOURCE_VERSION, **GRAPH.to_dict()}
    nodes: list[dict[str, Any]] = payload["nodes"]
    payload["nodes"] = [
        {**node, **_node_extras(node["id"], node["kind"], node["id"].partition(":")[2])}
        for node in nodes
    ]
    return payload


def method_graph_json() -> JSONResponse:
    """The whole method graph -- every process, technique and artifact node,
    every ``reads``/``produces``/``used_by``/``feeds`` edge -- as JSON. Frozen
    data: identical on every request, so nothing here reads a store or a clock."""
    return JSONResponse(graph_payload())


def install_method_map_json(app: FastAPI) -> None:
    """Add ``GET /map/graph.json`` straight to ``app``. No as-of: the route reads
    no store and no clock. See the module docstring for why this is a direct
    ``add_api_route`` call rather than an ``include_router`` one."""
    app.add_api_route("/map/graph.json", method_graph_json, methods=["GET"])
