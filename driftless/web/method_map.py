"""``GET /map``: one readable slice of the method graph drawn as an inline SVG
from ``graph_layout.LAYOUT``, plus a no-JS ``<details>`` alternative in words.

The default read is ``graph_views.overview()`` — the processes in lifecycle
order — because all 217 nodes at once came out thumbnail-sized and unlabelled.
``?focus=`` opens one node's ``graph_views.neighbourhood()``; ``?view=all`` is
the exhaustive read. The words below the SVG list every node and every tie
whichever slice is drawn, so nothing is reachable only through the picture.

``?project=&as_of=`` washes a process node with the SAME reading
``/projects/{id}/process-map`` prints for it (``views.state_word`` /
``CELL_RANK`` / ``CELL_MARK`` — the one place that vocabulary lives). A
node's own href carries the SAME ``?as_of=&project=`` (see ``node_href``), so
clicking off a washed map lands on the washed page too, not the theory one.
``?focus={id-or-slug}`` highlights one node and its ``GRAPH.neighbours``; a
word the graph answers to nothing highlights nothing rather than 404ing.

``?from=&to=`` draws the shortest ``feeds`` path between two processes;
``?group=``/``?area=`` draws one process group or knowledge area on its own.
Every one of these narrows through the same seam, ``graph_slice`` — a word
none of them answers to notices rather than 404ing or drawing nothing silent.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import date
from typing import Any, get_args

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.models import Project
from driftless.naming import humanize, technique_slug
from driftless.pmbok import state
from driftless.pmbok.artifact_definitions import ARTIFACTS
from driftless.pmbok.definitions import TECHNIQUES, TechniqueFamily
from driftless.pmbok.graph import GRAPH, Edge, EdgeKind
from driftless.pmbok.graph_layout import LAYOUT, Layout, focus_layout
from driftless.pmbok.graph_views import GraphView, neighbourhood, overview
from driftless.pmbok.model import KnowledgeArea, ProcessGroup
from driftless.pmbok.process_definitions import PROCESS_DEFINITIONS
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web import related
from driftless.web.templating import TEMPLATES
from driftless.web.views import CELL_MARK, CELL_RANK, LEGEND, state_word

#: A visible mark per node kind, so kind is never carried by wash alone.
KIND_MARK = {
    "process": "\N{WHITE MEDIUM SQUARE}",
    "technique": "\N{BLACK CIRCLE}",
    "artifact": "\N{BLACK DIAMOND}",
}
#: The verb an edge's own kind reads as, in the no-JS list of ties.
TIE_VERB = {
    "reads": "reads",
    "produces": "produces",
    "used_by": "is used by",
    "feeds": "feeds into",
    "part_of": "is part of",
}


def artifact_slug(key: str) -> str:
    """An artifact key as a URL word, the same transform ``technique_slug``
    applies (safe: ``ARTIFACT_KINDS`` keys are already unique). ``/artifacts/{slug}``
    may land in a sibling PR; every artifact node links there regardless."""
    return humanize(key).lower().replace(" ", "-")


def node_href(node_id: str, base: str = "") -> str:
    """``base`` is the SAME ``?as_of=&project=`` string ``overview_href`` and
    ``whole_graph_href`` carry, so a node's own link keeps the wash the map
    was drawn with instead of dropping it. Empty when there is none."""
    kind, _, key = node_id.partition(":")
    if kind == "process":
        return f"/pmbok/{key}{base}"
    if kind == "technique":
        return f"/techniques/{technique_slug(key)}{base}"
    return f"/artifacts/{artifact_slug(key)}{base}"


def tie_phrase(edge: Edge, target_label: str) -> str:
    """The one sentence an edge is described by, wherever it is printed."""
    verb = "may produce" if edge.kind == "produces" and edge.optional else TIE_VERB[edge.kind]
    return f"{verb} {target_label}"


def edge_legend() -> list[tuple[str, str]]:
    """``(css class, phrase)`` for every line the map's legend explains: one
    row per ``EdgeKind`` (``get_args(EdgeKind)``, so a new kind is required
    here without anyone editing this function), worded through the SAME
    ``tie_phrase`` the no-JS list and every ``<title>`` already use, plus one
    row for what a dashed line means regardless of kind."""
    entries = [
        (f"edge-{kind}", tie_phrase(Edge(source="", target="", kind=kind), "what it points to"))
        for kind in get_args(EdgeKind)
    ]
    entries.append(("edge-optional", "optional — may not exist for every project"))
    return entries


def _build_focus_index() -> dict[str, str]:
    """Every word a ``?focus=`` may name -> the node id it resolves to: the
    node's own id, its bare key, and (technique/artifact) its slug."""
    index: dict[str, str] = {}
    for node in GRAPH.nodes:
        kind, _, key = node.id.partition(":")
        index[node.id] = node.id
        index.setdefault(key, node.id)
        if kind == "technique":
            index.setdefault(technique_slug(key), node.id)
        elif kind == "artifact":
            index.setdefault(artifact_slug(key), node.id)
    return index


#: Built once at import from the frozen GRAPH, exactly like LAYOUT.
FOCUS_INDEX: dict[str, str] = _build_focus_index()

#: Every node's label, keyed by id -- the one place ``tie_phrase`` looks up an
#: edge's target label from, so a node's own title and its edges' titles are
#: worded off the SAME lookup.
_LABELS: dict[str, str] = {node.id: node.label for node in GRAPH.nodes}

#: One ``<title>`` per edge, worded through ``tie_phrase`` -- the SAME sentence
#: the no-JS list and every node panel already use. Built once at import,
#: exactly like ``FOCUS_INDEX``.
EDGE_TITLES: dict[Edge, str] = {
    edge: tie_phrase(edge, _LABELS[edge.target]) for edge in GRAPH.edges
}


def _render_nodes(
    focus_id: str | None, states: dict[str, tuple[str, str, str]] | None, base: str = ""
) -> list[dict[str, Any]]:
    """``states`` is ``{process_id: (word, rank, mark)}`` for the current
    project/as-of, built ONCE by the caller, or ``None`` for the theory read."""
    neighbours = GRAPH.neighbours(focus_id) if focus_id else ()
    outgoing: dict[str, list[str]] = {}
    for edge in GRAPH.edges:
        outgoing.setdefault(edge.source, []).append(tie_phrase(edge, _LABELS[edge.target]))

    nodes = []
    for node in GRAPH.nodes:
        kind, _, key = node.id.partition(":")
        wash = state_mark = None
        x, y = LAYOUT.positions[node.id]
        group = area = family = ""
        if kind == "process":
            process = PROCESS_DEFINITIONS[key].process
            group, area = process.group.value, process.area.value
            summary = PROCESS_DEFINITIONS[key].plain_summary
        elif kind == "technique":
            family = TECHNIQUES[key].family.value
            summary = TECHNIQUES[key].summary
        else:
            summary = ARTIFACTS[key].plain_summary
        # MP20: group/area (process) or family (technique) are otherwise carried
        # only by fill-colour and an ``aria-hidden`` band caption -- a
        # screen-reader reaches them here instead.
        if group:
            classification = f", {humanize(group)} / {humanize(area)}"
        elif family:
            classification = f", {humanize(family)}"
        else:
            classification = ""
        title = f"{node.label} — {kind}{classification}"
        if states is not None and kind == "process":
            word, rank, mark = states[key]
            wash, state_mark = rank, mark
            title += f" — {humanize(word)}"
        if node.id == focus_id:
            focus_class = "focus"
        elif node.id in neighbours:
            focus_class = "focus-neighbour"
        else:
            focus_class = ""
        nodes.append(
            {
                "id": node.id,
                "kind": kind,
                "label": node.label,
                "href": node_href(node.id, base),
                "box": LAYOUT.label_boxes[node.id],
                "x": x,
                "y": y,
                "mark": KIND_MARK[kind],
                "focus_class": focus_class,
                "title": title,
                "wash": wash,
                "state_mark": state_mark,
                "ties": tuple(outgoing.get(node.id, ())),
                "group": group,
                "area": area,
                "family": family,
                "summary": summary,
            }
        )
    return nodes


#: The one ``?view=`` word that asks for every node and every edge at once.
WHOLE_GRAPH = "all"

#: How many of the reader-facing project links ``/map`` prints inline before it
#: points at the dashboard instead of growing the page one link per project
#: forever. The dashboard ("/") is already the full portfolio list, so nothing
#: past this count is unreachable -- just not printed twice.
PROJECT_LIST_LIMIT = 20


def unknown_query_notice(
    focus: str | None,
    focus_id: str | None,
    view: str | None,
    from_word: str | None = None,
    from_id: str | None = None,
    to_word: str | None = None,
    to_id: str | None = None,
    path_found: bool = True,
    group: str | None = None,
    group_found: bool = True,
    area: str | None = None,
    area_found: bool = True,
) -> str | None:
    """What to tell a reader whose ``?focus=``/``?view=``/``?from=``/``?to=``/
    ``?group=``/``?area=`` named nothing this graph answers to -- never a
    404, since the map they land on (the overview, or whatever DID resolve)
    is still a useful page, just not the one their link asked for."""
    culprits = []
    if focus and focus_id is None:
        culprits.append(f'"{focus}" is not a node this map knows')
    if view is not None and view != WHOLE_GRAPH:
        culprits.append(f'"{view}" is not a map view this page knows')
    if from_word and from_id is None:
        culprits.append(f'"{from_word}" is not a node this map knows')
    if to_word and to_id is None:
        culprits.append(f'"{to_word}" is not a node this map knows')
    if from_id and to_id and not path_found:
        culprits.append(f'"{from_word}" has no feeds path to "{to_word}"')
    if group is not None and not group_found:
        culprits.append(f'"{group}" is not a process group this map knows')
    if area is not None and not area_found:
        culprits.append(f'"{area}" is not a knowledge area this map knows')
    if not culprits:
        return None
    return "; ".join(culprits).capitalize() + " — showing the map below instead."


def _process_slice(predicate: Callable[[Any], bool]) -> GraphView:
    """Every process ``predicate`` accepts, drawn with only the ``feeds`` ties
    internal to that set -- the same node-set-then-internal-edges shape
    ``graph_views`` builds every other slice with."""
    ids = {
        n.id
        for n in GRAPH.by_kind("process")
        if predicate(PROCESS_DEFINITIONS[n.id.partition(":")[2]].process)
    }
    nodes = tuple(n for n in GRAPH.nodes if n.id in ids)
    edges = tuple(e for e in GRAPH.edges if e.source in ids and e.target in ids)
    return GraphView(nodes=nodes, edges=edges)


def group_slice(group_value: str) -> GraphView | None:
    """One ``ProcessGroup``'s processes, or ``None`` for a word no group answers
    to -- the caller notices that rather than drawing an empty slice."""
    if group_value not in {g.value for g in ProcessGroup}:
        return None
    return _process_slice(lambda p: p.group.value == group_value)


def area_slice(area_value: str) -> GraphView | None:
    """One ``KnowledgeArea``'s processes, or ``None`` for a word no area answers
    to."""
    if area_value not in {a.value for a in KnowledgeArea}:
        return None
    return _process_slice(lambda p: p.area.value == area_value)


def path_slice(start_id: str, goal_id: str) -> GraphView | None:
    """The shortest route from ``start_id`` to ``goal_id`` over ``feeds`` edges
    alone, walked either direction (a route between two processes should not
    care which one happens to feed the other first) -- ``None`` when the two
    are not connected by any chain of ``feeds`` ties."""
    if start_id == goal_id:
        return GraphView(nodes=tuple(n for n in GRAPH.nodes if n.id == start_id), edges=())
    neighbours: dict[str, set[str]] = {}
    for edge in GRAPH.edges:
        if edge.kind != "feeds":
            continue
        neighbours.setdefault(edge.source, set()).add(edge.target)
        neighbours.setdefault(edge.target, set()).add(edge.source)
    came_from: dict[str, str] = {}
    frontier = deque([start_id])
    seen = {start_id}
    reached = False
    while frontier:
        current = frontier.popleft()
        if current == goal_id:
            reached = True
            break
        for neighbour in neighbours.get(current, ()):
            if neighbour not in seen:
                seen.add(neighbour)
                came_from[neighbour] = current
                frontier.append(neighbour)
    if not reached:
        return None
    path = [goal_id]
    while path[-1] != start_id:
        path.append(came_from[path[-1]])
    path.reverse()
    order = {node_id: i for i, node_id in enumerate(path)}
    ids = set(path)
    nodes = tuple(sorted((n for n in GRAPH.nodes if n.id in ids), key=lambda n: order[n.id]))
    edges = tuple(e for e in GRAPH.edges if e.source in ids and e.target in ids)
    return GraphView(nodes=nodes, edges=edges)


def graph_slice(
    view: str | None,
    focus_id: str | None,
    path_view: GraphView | None = None,
    group_view: GraphView | None = None,
    area_view: GraphView | None = None,
) -> tuple[str, GraphView]:
    """``(slice name, the slice)`` the SVG draws. ``?view=all`` wins outright;
    then a resolved ``?from=&to=`` path, then ``?group=``/``?area=``, then
    ``?focus=``'s ego network, then the process overview -- each already
    resolved (or ``None``) by the caller, so this function only picks."""
    if view == WHOLE_GRAPH:
        return WHOLE_GRAPH, GraphView(nodes=tuple(GRAPH.nodes), edges=GRAPH.edges)
    if path_view is not None:
        return "path", path_view
    if group_view is not None:
        return "group", group_view
    if area_view is not None:
        return "area", area_view
    if focus_id:
        return "focus", neighbourhood(focus_id)
    return "overview", overview()


def create_method_map_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """``GET /map``, the whole method graph drawn from ``LAYOUT``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/map", response_class=HTMLResponse)
    def method_map(
        request: Request,
        db: Db,
        project: int | None = None,
        focus: str | None = None,
        view: str | None = None,
        from_node: str | None = Query(None, alias="from"),
        to_node: str | None = Query(None, alias="to"),
        group: str | None = None,
        area: str | None = None,
        at: date = Depends(resolve_as_of),
    ) -> HTMLResponse:
        project_obj = fetch(db, Project, project) if project is not None else None
        states: dict[str, tuple[str, str, str]] | None = None
        if project_obj is not None:
            with state.prefetched(db, [project_obj]):
                process_states = state.project_process_states(project_obj, db, at)
            states = {}
            for process, process_state in process_states:
                word = state_word(process, process_state)
                states[process.id] = (word, CELL_RANK[word], CELL_MARK[word] or "")
        # Every project, for the reader-facing "wash it with a project" links a
        # missing ``?project=`` falls back to -- real links, never told to type
        # the query string themselves.
        all_projects = list(
            db.scalars(select(Project).order_by(Project.name, Project.id).limit(PROJECT_LIST_LIMIT))
        )
        focus_id = FOCUS_INDEX.get(focus or "")
        from_id = FOCUS_INDEX.get(from_node or "")
        to_id = FOCUS_INDEX.get(to_node or "")
        path_view = path_slice(from_id, to_id) if from_id and to_id else None
        group_view = group_slice(group) if group is not None else None
        area_view = area_slice(area) if area is not None else None
        notice = unknown_query_notice(
            focus,
            focus_id,
            view,
            from_node,
            from_id,
            to_node,
            to_id,
            path_view is not None,
            group,
            group_view is not None,
            area,
            area_view is not None,
        )
        slice_name, drawn = graph_slice(view, focus_id, path_view, group_view, area_view)
        # A focus view gets its OWN small layout: unlike the global grid (a
        # satellite's small dot/diamond, its label hidden at rest), a focus
        # page reveals every label at once, so its satellites need room at
        # their own label's width -- see graph_layout.focus_layout. Every
        # other slice keeps drawing from the shared global LAYOUT.
        local: Layout | None = (
            focus_layout(focus_id) if slice_name == "focus" and focus_id else None
        )
        base = f"?as_of={at.isoformat()}" + (f"&project={project_obj.id}" if project_obj else "")
        # NV24: a node's own href carries the project wash ONLY when there is
        # one -- unlike ``base`` above (the map's own nav links, which always
        # pin ``as_of`` even unwashed), an unwashed node keeps its plain,
        # query-free address.
        node_base = f"?as_of={at.isoformat()}&project={project_obj.id}" if project_obj else ""
        # Rendered ONCE, for EVERY node: the words below the SVG and the per-node
        # panels stay exhaustive whatever the picture narrows to, which is what keeps
        # the page whole with JavaScript off. The picture takes the slice's own nodes,
        # in the slice's own order.
        rendered = {node["id"]: node for node in _render_nodes(focus_id, states, node_base)}
        if local is not None:
            for node_id, (x, y) in local.positions.items():
                rendered[node_id] = {
                    **rendered[node_id],
                    "x": x,
                    "y": y,
                    "box": local.label_boxes[node_id],
                }
        viewbox = local.viewbox if local is not None else LAYOUT.viewbox
        edge_path = local.edge_paths if local is not None else LAYOUT.edge_paths
        # MP07: a chip that can only hide every drawn node is never rendered --
        # each dimension is read off what THIS slice drew (``drawn``, already in
        # hand above), not the full enum, so an overview of process-only nodes
        # offers no Technique/Artifact/family chip at all.
        drawn_kinds = {rendered[n.id]["kind"] for n in drawn.nodes}
        drawn_groups = {rendered[n.id]["group"] for n in drawn.nodes if rendered[n.id]["group"]}
        drawn_areas = {rendered[n.id]["area"] for n in drawn.nodes if rendered[n.id]["area"]}
        drawn_families = {rendered[n.id]["family"] for n in drawn.nodes if rendered[n.id]["family"]}
        context: dict[str, Any] = {
            "as_of": at.isoformat(),
            "project": project_obj,
            "focus_label": rendered[focus_id]["label"] if focus_id else None,
            "notice": notice,
            "projects": all_projects,
            "viewbox": f"0 0 {viewbox[0]} {viewbox[1]}",
            "nodes": [rendered[node.id] for node in drawn.nodes],
            "all_nodes": list(rendered.values()),
            "counts": drawn.counts(),
            "slice": slice_name,
            "overview_href": f"/map{base}",
            "whole_graph_href": f"/map{base}&view={WHOLE_GRAPH}",
            "focus_href_prefix": f"/map{base}&focus=",
            "size": viewbox,
            "kind_marks": KIND_MARK,
            "edge_legend": edge_legend(),
            "kinds": (
                ("process", "Processes"),
                ("technique", "Techniques"),
                ("artifact", "Artifacts"),
            ),
            "edges": drawn.edges,
            "edge_titles": EDGE_TITLES,
            "edge_path": edge_path,
            "kind_filters": [
                (value, label)
                for value, label in (
                    ("process", "Process"),
                    ("technique", "Technique"),
                    ("artifact", "Artifact"),
                )
                if value in drawn_kinds
            ],
            "group_filters": [
                (g.value, humanize(g.value)) for g in ProcessGroup if g.value in drawn_groups
            ],
            # NOT ``group_filters``: the five bands are the map's fixed frame, drawn
            # from EVERY process so a narrow slice puts its three groups where the
            # overview puts them. Sharing the narrowed chip list would shift
            # ``loop.first``/``loop.last``, restripe the shading and silently give a
            # one-group slice a single band spanning the whole viewbox.
            "band_groups": [(g.value, humanize(g.value)) for g in ProcessGroup],
            "area_filters": [
                (a.value, humanize(a.value)) for a in KnowledgeArea if a.value in drawn_areas
            ],
            "family_filters": [
                (f.value, humanize(f.value)) for f in TechniqueFamily if f.value in drawn_families
            ],
            "show_flow_only": any(edge.kind != "feeds" for edge in drawn.edges),
            "legend": LEGEND,
            "related": related.for_map(
                project_id=project_obj.id if project_obj else None,
                project_name=project_obj.name if project_obj else None,
            ),
        }
        return TEMPLATES.TemplateResponse(request, "method_map.html", context)

    return router
