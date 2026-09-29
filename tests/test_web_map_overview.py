"""``GET /map`` reads as a process overview, with the whole graph one link away.

The map used to draw every node and edge into one scaled picture: thumbnail-sized at
390px, most labels hidden until hover, so a reader could see marks existed but could
not identify one. Every number asserted below is computed from ``GRAPH`` through
``graph_views``, never typed here, so a growing catalog keeps the page honest.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from driftless.pmbok.graph import GRAPH
from driftless.pmbok.graph_layout import LAYOUT, focus_layout
from driftless.pmbok.graph_views import GraphView, neighbourhood, overview
from driftless.web.method_map import tie_phrase
import test_web_pages
from test_web_method_map import _body
from test_web_pages import Q

client, db = test_web_pages.client, test_web_pages.db

_NODE = re.compile(r'<g class="node[^"]*" data-node="([^"]+)"')
_EDGE = re.compile(r'<path class="edge[^"]*" d="[^"]*" data-from="([^"]+)" data-to="([^"]+)"')
_MAP_SVG = re.compile(r"<svg\b[^>]*aria-label=\"The method graph[^\"]*\"[^>]*>")


def _drawn(body: str) -> tuple[list[str], list[tuple[str, str]]]:
    return _NODE.findall(body), _EDGE.findall(body)


def _sentence(counts: object) -> str:
    c = counts
    return f"Showing {c.nodes} of {c.total_nodes} nodes; {c.edges} relevant ties."  # type: ignore[attr-defined]


def test_the_default_map_draws_the_process_overview_and_not_every_node(
    client: TestClient,
) -> None:
    view = overview()
    assert len(view.nodes) < len(GRAPH.nodes), "vacuous: the overview is the whole graph"
    nodes, edges = _drawn(_body(client, f"/map{Q}"))
    assert nodes == [n.id for n in view.nodes]
    assert edges == [(e.source, e.target) for e in view.edges]


def test_the_whole_graph_is_still_reachable_by_name(client: TestClient) -> None:
    nodes, edges = _drawn(_body(client, f"/map{Q}&view=all"))
    assert nodes == [n.id for n in GRAPH.nodes]
    assert edges == [(e.source, e.target) for e in GRAPH.edges]


def test_focusing_a_node_draws_that_node_s_neighbourhood_and_nothing_else(
    client: TestClient,
) -> None:
    process = GRAPH.by_kind("process")[0]
    view = neighbourhood(process.id)
    assert len(view.nodes) < len(GRAPH.nodes), "vacuous: the ego network is the whole graph"
    nodes, edges = _drawn(_body(client, f"/map{Q}&focus={process.id}"))
    assert nodes == [n.id for n in view.nodes]
    assert edges == [(e.source, e.target) for e in view.edges]
    # A word the graph answers to nothing falls back to the overview, never a 404.
    stale, _ = _drawn(_body(client, f"/map{Q}&focus=not-a-real-node"))
    assert stale == [n.id for n in overview().nodes]


def test_the_page_states_what_it_is_showing_composed_from_the_measured_counts(
    client: TestClient,
) -> None:
    process = GRAPH.by_kind("process")[0]
    whole = GraphView(nodes=tuple(GRAPH.nodes), edges=GRAPH.edges)
    for query, view in (
        ("", overview()),
        ("&view=all", whole),
        (f"&focus={process.id}", neighbourhood(process.id)),
    ):
        body = _body(client, f"/map{Q}{query}")
        assert _sentence(view.counts()) in body, query
    assert _sentence(overview().counts()) != _sentence(whole.counts()), (
        "vacuous: the overview and the whole graph would print the same sentence"
    )


def test_every_view_keeps_the_no_js_list_of_every_node_and_every_tie(
    client: TestClient,
) -> None:
    """The no-JS ``<details>`` list (reached with or without a script) stays
    exhaustive whatever slice is drawn. The per-node ``<aside>`` panels are
    JS-only — never reachable at all with JS off — so they are pared to the
    drawn slice instead of carrying the whole catalog on every request; only
    ``view=all`` draws every node, so only there do panels cover every node."""
    labels = {n.id: n.label for n in GRAPH.nodes}
    process = GRAPH.by_kind("process")[0]
    for query in ("", "&view=all", f"&focus={process.id}"):
        body = _body(client, f"/map{Q}{query}")
        for edge in GRAPH.edges:
            assert tie_phrase(edge, labels[edge.target]) in body, (query, edge.source)
    body = _body(client, f"/map{Q}&view=all")
    for node in GRAPH.nodes:
        assert f'data-panel-for="{node.id}"' in body, node.id


def test_every_node_offers_a_link_that_opens_its_own_neighbourhood(client: TestClient) -> None:
    body = _body(client, f"/map{Q}")
    missing = [n.id for n in GRAPH.nodes if f"&amp;focus={n.id}" not in body]
    assert not missing, f"{len(missing)} nodes cannot be expanded from the page, e.g. {missing[:3]}"


def test_the_drawing_the_server_sends_says_what_it_is_and_carries_its_own_size(
    client: TestClient,
) -> None:
    """Three facts the element itself carries, a reader with no script running getting
    nothing else: which slice this is and the way back (``map.js`` reads both rather
    than building an address); ``.map-narrow``, map.css's class for showing a
    technique/artifact label at rest, since a slice is narrow by definition and must
    not wait for a script to count; and its own pixel size, a viewBox alone having
    scaled the drawing to the column and made it a thumbnail at 390px. A ``focus``
    slice carries its OWN size, off ``graph_layout.focus_layout`` -- a local
    layout sized to the one process neighbourhood it draws, never the shared
    global ``LAYOUT`` every other slice uses (widening a focused process's own
    satellites must not grow every other view's drawing). That size rides on
    ``data-width``/``data-height``, never the ``width``/``height`` attributes a
    fixed-size drawing used to hardcode -- those made the map 4+ screens of sideways
    scroll on a phone. The SVG itself scales to the column (``map-svg``, CSS
    ``width: 100%``) with a ``min-width`` floor keeping labels legible, and the
    element carries no ``width``/``height`` attribute at all."""
    global_width, global_height = LAYOUT.viewbox
    focus_width, focus_height = focus_layout("process:4.1").viewbox
    for query, name, narrow, width, height in (
        ("", "overview", True, global_width, global_height),
        ("&view=all", "all", False, global_width, global_height),
        ("&focus=4.1", "focus", True, focus_width, focus_height),
    ):
        found = _MAP_SVG.search(_body(client, f"/map{Q}{query}"))
        assert found, query
        tag = found.group(0)
        assert f'data-slice="{name}"' in tag and 'data-overview="/map?' in tag, tag
        assert ("map-narrow" in tag) is narrow, tag
        assert f'data-width="{width}"' in tag and f'data-height="{height}"' in tag, tag
        assert "map-svg" in tag, tag
        assert not re.search(r'(?<!data-)\bwidth="\d', tag), tag
        assert not re.search(r'(?<!data-)\bheight="\d', tag), tag


def test_every_kind_of_node_can_be_focused_not_only_a_process(client: TestClient) -> None:
    """The page offers a focus link for EVERY node it draws (the test above pins
    that), so every one of those links must open. ``focus_layout`` used to look its
    anchor up in a process-only index, so focusing a technique or an artifact raised
    ``KeyError`` while focusing a process worked -- the page offered a link to a
    picture it could not draw, and only a caller that followed an artifact's link
    ever found out."""
    kinds = sorted({node.kind for node in GRAPH.nodes})
    assert kinds == ["artifact", "process", "technique"], kinds
    for kind in kinds:
        node = GRAPH.by_kind(kind)[0]
        page = client.get(f"/map{Q}&focus={node.id}")
        assert page.status_code == 200, f"focusing {node.id} -> {page.status_code}"
