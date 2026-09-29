"""``GET /map``: the method graph drawn as one page (M.3).

Every ``graph.GRAPH`` node and edge is walked off the live registry, so a catalog
that grows a process, technique or artifact is required here without anyone
editing this file. The project overlay is checked against
``/projects/{id}/process-map``'s own cell for the same process/as-of — never a
second reading of the same fact.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.models import Project
from driftless.naming import humanize, technique_slug
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.graph import GRAPH
from driftless.pmbok.graph_layout import LAYOUT
from driftless.pmbok.graph_views import neighbourhood
from driftless.pmbok.process_definitions import PROCESS_DEFINITIONS
from driftless.web.method_map import (
    KIND_MARK,
    PROJECT_LIST_LIMIT,
    TIE_VERB,
    artifact_slug,
    edge_legend,
    tie_phrase,
)
import test_web_pages
from test_web_pages import AS_OF
from test_web_responsive import BREAKPOINT

client, db = test_web_pages.client, test_web_pages.db
Q = f"as_of={AS_OF.isoformat()}"
_STYLESHEET = (
    Path(__file__).resolve().parents[1] / "driftless" / "web" / "static" / "driftless.css"
).read_text()
_MAP_CSS = (
    Path(__file__).resolve().parents[1] / "driftless" / "web" / "static" / "map.css"
).read_text()
_DASH = re.compile(r"\.edge-(\w+)\s*\{[^}]*stroke-dasharray:\s*([^;]+);")

_NODE = re.compile(
    r'<g class="node[^"]*" data-node="([^"]+)" data-kind="([^"]+)" data-label="[^"]*">'
    r'\s*<a href="([^"]+)">',
    re.S,
)
_EDGE = re.compile(r'<path class="edge[^"]*" d="[^"]*" data-from="([^"]+)" data-to="([^"]+)"')
_TITLE = re.compile(r"<title>([^<]*)</title>")
_GRID_CELL = re.compile(r'<span class="badge st-([a-z]+)" title="([^"]*)">(\S+) ')


def _body(client: TestClient, path: str) -> str:
    page = client.get(path)
    assert page.status_code == 200, page.text[:300]
    return page.text


def _node_html(body: str, node_id: str) -> tuple[str, str]:
    """``(class attribute, inner markup)`` of one node's ``<g>`` through its
    ``</g>``, which never nests another ``<g>``."""
    match = re.search(
        rf'<g class="([^"]*)" data-node="{re.escape(node_id)}" data-kind="[^"]*" data-label="[^"]*">',
        body,
    )
    assert match, node_id
    return match.group(1), body[match.end() : body.index("</g>", match.end())]


def _href(node_id: str) -> str:
    kind, _, key = node_id.partition(":")
    if kind == "process":
        return f"/pmbok/{key}"
    if kind == "technique":
        return f"/techniques/{technique_slug(key)}"
    return f"/artifacts/{artifact_slug(key)}"


def test_every_node_and_edge_is_drawn_exactly_once_and_links_to_its_own_page(
    client: TestClient,
) -> None:
    """``?view=all`` is the exhaustive read; the default is the process overview
    (:mod:`test_web_map_overview`), so totality is asked of the view that claims it."""
    body = _body(client, f"/map?view=all&{Q}")
    nodes, edges = _NODE.findall(body), _EDGE.findall(body)
    assert len(nodes) == len(GRAPH.nodes) and len(edges) == len(GRAPH.edges)
    assert {(i, k) for i, k, _ in nodes} == {(n.id, n.kind) for n in GRAPH.nodes}
    assert {(i, h) for i, _, h in nodes} == {(n.id, _href(n.id)) for n in GRAPH.nodes}
    assert sorted(edges) == sorted((e.source, e.target) for e in GRAPH.edges)


def test_the_layout_positions_every_drawn_node(client: TestClient) -> None:
    body = _body(client, f"/map?view=all&{Q}")
    for node in GRAPH.nodes:
        x, y = LAYOUT.positions[node.id]
        _, inner = _node_html(body, node.id)
        assert f'x="{x}"' in inner and f'y="{y}"' in inner, node.id


def test_the_map_regenerates_byte_identically(client: TestClient) -> None:
    first = client.get(f"/map?{Q}")
    assert first.content == client.get(f"/map?{Q}").content
    with_project = client.get(f"/map?project=1&{Q}")
    assert with_project.content == client.get(f"/map?project=1&{Q}").content


def test_no_raw_identifier_leaks_into_the_pages_own_text(client: TestClient) -> None:
    """Every attribute value is an address, never prose. Strip every tag and
    attribute value; no underscored key may remain in what is left."""
    body = _body(client, f"/map?{Q}")
    visible = re.sub(r"<[a-zA-Z!][^>]*>", "", re.sub(r'="[^"]*"', "", body))
    identifier_keys = [n.id.partition(":")[2] for n in GRAPH.nodes if "_" in n.id]
    assert identifier_keys and not [key for key in identifier_keys if key in visible]


def test_the_three_kinds_carry_a_distinct_mark_never_colour_alone() -> None:
    assert len(set(KIND_MARK.values())) == len(KIND_MARK) == 3


def test_each_tie_kind_has_its_own_dash_pattern_never_colour_alone() -> None:
    """Tie kind (``data-tie``) survives the colour thrown away too: each of the
    four ``TIE_VERB`` kinds gets its own ``.edge-{kind}`` stroke-dasharray, read
    straight off the live stylesheet rather than pinned as a second list."""
    dashes = dict(_DASH.findall(_STYLESHEET))
    assert set(dashes) == set(TIE_VERB), (
        f"driftless.css dashes {sorted(dashes)}, the tie vocabulary is {sorted(TIE_VERB)}"
    )
    assert len(set(dashes.values())) == len(TIE_VERB), (
        f"two tie kinds share a dash pattern: {dashes}"
    )


def test_the_two_dotted_ties_read_apart_at_the_edge_stroke_width() -> None:
    """MP08: ``used_by`` (fine dots) and ``part_of`` (tight dots, wide gaps) used
    to share the same 4px dash+gap period (2+2 and 1+3) -- at .75px stroke-width
    a reader cannot tell a short cycle repeated from a short cycle repeated the
    same amount. Every dotted/dashed kind must repeat on its own period."""
    dashes = dict(_DASH.findall(_STYLESHEET))
    periods = {
        kind: sum(int(n) for n in pattern.split())
        for kind, pattern in dashes.items()
        if pattern.strip() != "none"
    }
    seen: dict[int, str] = {}
    collisions = []
    for kind, period in periods.items():
        if period in seen:
            collisions.append((kind, seen[period], period))
        seen[period] = kind
    assert not collisions, f"tie kinds sharing a dash period: {collisions}"


def test_every_tie_kind_gets_its_own_arrowhead(client: TestClient) -> None:
    """MP08: a dash pattern alone still leaves a reader guessing which end of a
    tie is the source and which is the target. Every edge kind gets its own
    marker, defined once in the drawing's own <defs> and applied by CSS -- never
    a per-path attribute the template would have to repeat 200+ times."""
    body = _body(client, f"/map?view=all&{Q}")
    for kind in TIE_VERB:
        assert f'id="arrow-{kind}"' in body, f'no <marker id="arrow-{kind}"> in the drawing'
        rule = re.search(rf"\.edge-{kind}\s*\{{[^}}]*}}", _STYLESHEET) or re.search(
            rf"\.edge-{kind}\s*\{{[^}}]*}}", _MAP_CSS
        )
        assert rule and f"url(#arrow-{kind})" in rule.group(0), (
            f".edge-{kind} has no marker-end pointing at its own arrowhead"
        )


def test_the_keyboard_focus_ring_reads_apart_from_the_url_focus_ring() -> None:
    """MP27: driftless.css's `.node.focus`/`.node.focus-neighbour` (the ``?focus=``
    URL ring) and map.css's own `:focus-visible` ring both thicken the same stroke
    to 3.5 -- a keyboard user tabbed onto the node the URL already highlights would
    see one ring standing for two different reasons. The keyboard ring must carry
    its own colour (the site's one --focus token, never a literal) and dasharray
    so the two read apart even with colour off."""
    rule = re.search(r"\.node a:focus-visible \.node-shape\s*\{([^}]*)\}", _MAP_CSS)
    assert rule, "no keyboard focus-visible rule on .node-shape"
    declarations = rule.group(1)
    assert "stroke: var(--focus)" in declarations, (
        f"keyboard focus ring must use the --focus token, not a literal: {declarations!r}"
    )
    assert re.search(r"stroke-dasharray:\s*\S", declarations), (
        f"keyboard focus ring needs its own dasharray to read apart from ?focus=: {declarations!r}"
    )


def test_the_legend_process_swatch_is_a_colour_a_process_can_actually_wear(
    client: TestClient,
) -> None:
    """MP30: every process is tinted by its own knowledge area
    (``.node-shape[data-area=...]``); the flat grey ``#8c8c8c`` the legend used to
    show is a fill NO process ever draws -- only a "general" technique does. The
    swatch must be one of the real area tints, not that neutral."""
    area_fills = set(
        re.findall(r'\.node-shape\[data-area="[a-z]+"\]\s*\{\s*fill:\s*(#[0-9a-f]{6})', _MAP_CSS)
    )
    assert area_fills, "no knowledge-area tints found in map.css"
    process_fill = re.search(r"\.map-legend-process\s*\{[^}]*fill:\s*(#[0-9a-f]{6})", _MAP_CSS)
    assert process_fill, "no .map-legend-process fill"
    assert process_fill.group(1) in area_fills, (
        f"legend Process swatch is {process_fill.group(1)!r}, a colour no process ever "
        f"wears -- pick one of the real area tints {sorted(area_fills)}"
    )


def test_the_no_js_details_list_every_tie_the_graph_has(client: TestClient) -> None:
    body = _body(client, f"/map?{Q}")
    labels = {n.id: n.label for n in GRAPH.nodes}
    for edge in GRAPH.edges:
        assert tie_phrase(edge, labels[edge.target]) in body, (edge.source, edge.target, edge.kind)


def test_the_legend_explains_every_tie_kind_and_the_optional_dash(client: TestClient) -> None:
    """DH07: the legend's shapes and fills already say what they mean; the
    lines get the same treatment -- one entry per ``EdgeKind`` plus one for
    what a dashed line means, worded through ``edge_legend()``."""
    body = _body(client, f"/map?{Q}")
    legend = re.search(r'<dl class="legend map-legend">.*?</dl>', body, re.S)
    assert legend, "no map legend"
    inner = legend.group(0)
    assert "<dt>Tie (line)</dt>" in inner
    entries = edge_legend()
    assert len(entries) == len(TIE_VERB) + 1
    for css_class, phrase in entries:
        assert f'class="map-legend-edge {css_class}"' in inner and phrase in inner
    assert "edge-optional" in {css_class for css_class, _ in entries}


def test_an_optional_feeds_edge_is_drawn_dashed(client: TestClient) -> None:
    optional_feeds = next(e for e in GRAPH.edges if e.kind == "feeds" and e.optional)
    certain_feeds = next(e for e in GRAPH.edges if e.kind == "feeds" and not e.optional)
    body = _body(client, f"/map?view=all&{Q}")
    optional_path = re.search(
        rf'<path class="([^"]*)" d="[^"]*" data-from="{re.escape(optional_feeds.source)}" '
        rf'data-to="{re.escape(optional_feeds.target)}"',
        body,
    )
    certain_path = re.search(
        rf'<path class="([^"]*)" d="[^"]*" data-from="{re.escape(certain_feeds.source)}" '
        rf'data-to="{re.escape(certain_feeds.target)}"',
        body,
    )
    assert optional_path and "edge-optional" in optional_path.group(1)
    assert certain_path and "edge-optional" not in certain_path.group(1)


def test_a_project_overlay_reuses_the_process_map_s_own_reading(client: TestClient) -> None:
    grid_body = _body(client, f"/projects/1/process-map?{Q}")
    map_body = _body(client, f"/map?project=1&{Q}")
    grid_cells = {pid: (rank, s) for rank, s, pid in _GRID_CELL.findall(grid_body)}
    assert grid_cells, "vacuous: the process-map grid rendered no cell"
    for pid, (rank, s) in grid_cells.items():
        classes, inner = _node_html(map_body, f"process:{pid}")
        title = _TITLE.search(inner)
        assert f"st-{rank}" in classes and title and humanize(s) in title.group(1), (pid, rank, s)


def test_the_washed_map_legends_its_states(client: TestClient) -> None:
    """MP18: a washed process node prints a state mark, but until now the legend
    never explained what a state mark means — only shape, area and tie."""
    from driftless.web.views import LEGEND

    unwashed = _body(client, f"/map?{Q}")
    assert "<dt>State</dt>" not in unwashed

    washed = _body(client, f"/map?project=1&{Q}")
    legend = re.search(r'<dl class="legend map-legend">.*?</dl>', washed, re.S)
    assert legend, "no map legend"
    inner = legend.group(0)
    assert "<dt>State</dt>" in inner
    for st, rank, mark in LEGEND:
        assert f'st-{rank}"' in inner and mark in inner and humanize(st) in inner


def test_the_map_says_how_to_read_itself(client: TestClient) -> None:
    """DH11: an inline "How to read this page" block, so a first-time reader is
    not left to infer shapes, lines and controls from the picture alone."""
    body = _body(client, f"/map?{Q}")
    assert "<summary>How to read this page</summary>" in body


def test_the_map_collapses_its_shapes_and_lines_explainer(client: TestClient) -> None:
    """MP29: the long shapes/lines paragraph is folded under its own
    ``<details>`` so the drawing the page exists for is not pushed below five
    paragraphs, 28 chips and 19 legend rows of prose first."""
    body = _body(client, f"/map?{Q}")
    match = re.search(
        r"<details>\s*<summary>How to read this map</summary>(?P<inner>.*?)</details>",
        body,
        re.S,
    )
    assert match, "no collapsed shapes/lines explainer"
    assert "Every shape links to its own page" in match.group("inner")


def test_the_map_relates_out_to_the_catalogs_it_draws_from(client: TestClient) -> None:
    """MP11: the map is anchored to the reference it summarises."""
    unwashed = _body(client, f"/map?{Q}")
    assert '<section class="related"' in unwashed
    assert 'href="/pmbok"' in unwashed
    assert 'href="/techniques"' in unwashed
    assert 'href="/artifacts"' in unwashed
    assert 'href="/process-map"' in unwashed

    washed = _body(client, f"/map?project=1&{Q}")
    assert 'href="/projects/1/process-map"' in washed


def test_focus_highlights_the_node_and_its_neighbours_but_a_stale_word_404s_nothing(
    client: TestClient,
) -> None:
    process = GRAPH.by_kind("process")[0]
    body = _body(client, f"/map?focus={process.id}&{Q}")
    classes, _ = _node_html(body, process.id)
    assert re.search(r"\bfocus\b", classes), classes
    for neighbour in GRAPH.neighbours(process.id):
        n_classes, _ = _node_html(body, neighbour)
        assert "focus-neighbour" in n_classes, neighbour
    miss = client.get(f"/map?focus=not-a-real-node&{Q}")
    assert miss.status_code == 200 and "focus-neighbour" not in miss.text


def test_a_process_and_a_technique_page_each_link_back_to_the_map(client: TestClient) -> None:
    process = GRAPH.by_kind("process")[0].id.partition(":")[2]
    assert f'href="/map?focus=process:{process}"' in _body(client, f"/pmbok/{process}")
    key = GRAPH.by_kind("technique")[0].id.partition(":")[2]
    body = _body(client, f"/techniques/{technique_slug(key)}")
    assert f'href="/map?focus=technique:{key}"' in body


def test_the_map_is_reachable_from_the_primary_nav(client: TestClient) -> None:
    assert 'href="/map"' in _body(client, "/")


def test_panels_render_only_for_the_drawn_slice_not_the_whole_catalog(
    client: TestClient,
) -> None:
    """A focus view draws a handful of nodes; the per-node ``<aside>`` panels
    (JS-only, never reachable with JS off) should not carry the other ~200 the
    picture never shows — that is page weight the drawn slice cannot use."""
    process = GRAPH.by_kind("process")[0]
    body = _body(client, f"/map?focus={process.id}&{Q}")
    drawn_ids = {n.id for n in neighbourhood(process.id).nodes}
    assert len(drawn_ids) < len(GRAPH.nodes), "vacuous: the neighbourhood is the whole graph"
    for node in GRAPH.nodes:
        has_panel = f'data-panel-for="{node.id}"' in body
        assert has_panel == (node.id in drawn_ids), node.id


def test_an_unrecognised_focus_or_view_notices_instead_of_silently_ignoring_it(
    client: TestClient,
) -> None:
    stale_focus = _body(client, f"/map?focus=not-a-real-node&{Q}")
    assert "not-a-real-node" in stale_focus and 'class="map-notice"' in stale_focus
    stale_view = _body(client, f"/map?view=bogus&{Q}")
    assert "bogus" in stale_view and 'class="map-notice"' in stale_view
    clean = _body(client, f"/map?{Q}")
    assert 'class="map-notice"' not in clean


def test_the_project_list_is_bounded_but_the_rest_stay_reachable(
    client: TestClient, db: Session
) -> None:
    for i in range(PROJECT_LIST_LIMIT + 5):
        db.add(Project(name=f"Extra {i}", portfolio_id=1, delivery_mode="predictive"))
    db.commit()
    body = _body(client, f"/map?{Q}")
    listed = re.findall(r'href="/map\?project=(\d+)&amp;as_of=', body)
    assert 0 < len(listed) <= PROJECT_LIST_LIMIT
    assert 'href="/"' in body


def test_the_per_node_panel_is_a_sticky_announcing_column(client: TestClient) -> None:
    """MP04: whatever slice is drawn, its per-node ``<aside class="map-panel">``
    blocks sit beside the drawing, in one persistent ``role="status"`` container
    map.js's existing ``setPanel()`` un-hides a child of — never a container that
    itself toggles ``hidden``, since a live region established the same moment it
    appears is exactly the case screen readers unreliably announce. The drawing
    and the panel column share one flex wrapper so map.css can pin the column
    (`position: sticky`) without a script; the same wrapper collapses to a stack
    under the site's one existing 60rem breakpoint (driftless.css BREAKPOINT),
    never a new one. ``?view=all`` draws all 217 nodes, so the panel count check
    below still exercises the full column."""
    body = _body(client, f"/map?view=all&{Q}")
    layout = re.search(
        r'<div class="map-layout">.*?<div class="scroll-x"[^>]*>.*?</div>\s*'
        r'<div class="map-panels"[^>]*role="status"[^>]*aria-live="polite"[^>]*>'
        r"(.*?)</div>\s*</div>",
        body,
        re.S,
    )
    assert layout, "no .map-layout wrapping a .scroll-x drawing and a live .map-panels column"
    panels_html = layout.group(1)
    assert panels_html.count('<aside class="map-panel"') > 200, "panels must stay inside the column"
    assert 'aria-live="polite"' not in panels_html, (
        "aria-live belongs on the stable .map-panels wrapper, never re-declared on the "
        "individual panels that get hidden/unhidden"
    )
    assert ".map-panels {" in _MAP_CSS and "position: sticky" in _MAP_CSS
    assert BREAKPOINT in _MAP_CSS, "the panel column must collapse at the site's one breakpoint"


def test_every_edge_carries_the_same_tie_sentence_hovering_the_line_reads(
    client: TestClient,
) -> None:
    """MP06/docs/user-guide.md: "Hover ... for the plain-English sentence the
    line stands for" -- the edge itself needs a ``<title>``, worded through the
    SAME ``tie_phrase`` the no-JS list and node panels already use."""
    body = _body(client, f"/map?view=all&{Q}")
    labels = {n.id: n.label for n in GRAPH.nodes}
    for edge in GRAPH.edges:
        match = re.search(
            rf'<path class="edge[^"]*" d="[^"]*" data-from="{re.escape(edge.source)}" '
            rf'data-to="{re.escape(edge.target)}"[^>]*>\s*<title>([^<]*)</title>\s*</path>',
            body,
        )
        assert match, (edge.source, edge.target)
        assert match.group(1) == tie_phrase(edge, labels[edge.target]), (
            edge.source,
            edge.target,
        )


def test_a_node_panel_lists_the_ties_it_is_the_source_of(client: TestClient) -> None:
    """MP06: opening either end of a tie ("open ... for the plain-English
    sentence the line stands for") means the node's own panel, not only the
    no-JS details list, carries the sentences for the edges it sources."""
    body = _body(client, f"/map?view=all&{Q}")
    labels = {n.id: n.label for n in GRAPH.nodes}
    source_with_ties = next(e.source for e in GRAPH.edges)
    edges = [e for e in GRAPH.edges if e.source == source_with_ties]
    panel = re.search(
        rf'<aside class="map-panel" data-panel-for="{re.escape(source_with_ties)}"[^>]*>(.*?)</aside>',
        body,
        re.S,
    )
    assert panel, source_with_ties
    for edge in edges:
        assert tie_phrase(edge, labels[edge.target]) in panel.group(1), edge


def test_a_process_nodes_title_names_its_group_and_area(client: TestClient) -> None:
    """MP20: group and area (fill-colour only, and the band captions are
    ``aria-hidden``) reach a screen-reader through the node's own ``<title>``."""
    process = GRAPH.by_kind("process")[0]
    key = process.id.partition(":")[2]
    definition = PROCESS_DEFINITIONS[key].process
    group, area = humanize(definition.group.value), humanize(definition.area.value)
    body = _body(client, f"/map?view=all&{Q}")
    _, inner = _node_html(body, process.id)
    title = _TITLE.search(inner)
    assert title and f"{group} / {area}" in title.group(1), title


def test_a_technique_nodes_title_names_its_family(client: TestClient) -> None:
    technique = GRAPH.by_kind("technique")[0]
    key = technique.id.partition(":")[2]
    family = humanize(TECHNIQUES[key].family.value)
    body = _body(client, f"/map?view=all&{Q}")
    _, inner = _node_html(body, technique.id)
    title = _TITLE.search(inner)
    assert title and family in title.group(1), title


def test_wash_is_explained_in_plain_language_where_it_is_used(client: TestClient) -> None:
    """X04: "washed" is this page's own jargon and must not appear unexplained,
    whether or not a project is selected."""
    without_project = _body(client, f"/map?{Q}")
    with_project = _body(client, f"/map?project=1&{Q}")
    explains_wash = re.compile(r"[Ww]ash(?:ing|ed)?\b[^.]*\bmeans\b", re.S)
    for body in (without_project, with_project):
        assert explains_wash.search(body), body


def test_a_project_washed_map_links_back_to_that_project_s_wizard(client: TestClient) -> None:
    """NV19: the wizard links to the map (wizard.html); the reverse link only
    makes sense once a project is selected, since that is the only read where a
    wizard step is a real address."""
    without_project = _body(client, f"/map?{Q}")
    assert "/wizard" not in without_project
    with_project = _body(client, f"/map?project=1&{Q}")
    assert f'href="/projects/1/wizard?as_of={AS_OF.isoformat()}"' in with_project


def test_a_node_href_carries_the_project_wash_it_was_drawn_with(client: TestClient) -> None:
    """NV24: the map's own links (``overview_href``/``whole_graph_href``) keep
    ``?project=`` and ``?as_of=`` through a hop; a node's own href must too, or
    clicking a process off a washed map lands on the unwashed page."""
    process = GRAPH.by_kind("process")[0]
    body = _body(client, f"/map?project=1&{Q}")
    _, inner = _node_html(body, process.id)
    href = re.search(r'<a href="([^"]+)">', inner)
    assert href
    assert href.group(1) == f"{_href(process.id)}?as_of={AS_OF.isoformat()}&amp;project=1"


def _feeds_chain() -> tuple[str, str, str]:
    """Three process ids ``a, b, c`` two ``feeds`` hops apart with no direct
    ``feeds`` tie between ``a`` and ``c``, and exactly ONE node ``b`` bridging
    them -- so the shortest ``feeds`` route between ``a`` and ``c`` is
    unambiguous, whichever order a BFS happens to visit neighbours in."""
    feeds = {(e.source, e.target) for e in GRAPH.edges if e.kind == "feeds"}
    undirected: dict[str, set[str]] = {}
    for s, t in feeds:
        undirected.setdefault(s, set()).add(t)
        undirected.setdefault(t, set()).add(s)
    direct = feeds | {(t, s) for s, t in feeds}
    for a, a_neighbours in undirected.items():
        for c, c_neighbours in undirected.items():
            if c == a or (a, c) in direct:
                continue
            bridges = a_neighbours & c_neighbours
            if len(bridges) == 1:
                return a, next(iter(bridges)), c
    raise AssertionError("no unique 2-hop feeds chain in GRAPH")


def test_from_and_to_draws_only_the_feeds_path_between_them(client: TestClient) -> None:
    a, b, c = _feeds_chain()
    body = _body(client, f"/map?from={a}&to={c}&{Q}")
    nodes = {i for i, _, _ in _NODE.findall(body)}
    assert nodes == {a, b, c}, nodes
    edges = {frozenset(pair) for pair in _EDGE.findall(body)}
    assert edges == {frozenset((a, b)), frozenset((b, c))}, edges


def test_an_unresolved_from_or_to_notices_instead_of_500ing(client: TestClient) -> None:
    body = _body(client, f"/map?from=not-a-real-node&to=also-fake&{Q}")
    assert body
    assert "not-a-real-node" in body and "also-fake" in body
    assert 'class="map-notice"' in body


def test_group_and_area_narrow_the_drawing_and_an_unknown_one_notices(client: TestClient) -> None:
    process = GRAPH.by_kind("process")[0]
    definition = PROCESS_DEFINITIONS[process.id.partition(":")[2]].process
    group_value, area_value = definition.group.value, definition.area.value

    def _process_ids(predicate: object) -> set[str]:
        return {
            n.id
            for n in GRAPH.by_kind("process")
            if predicate(PROCESS_DEFINITIONS[n.id.partition(":")[2]].process)  # type: ignore[operator]
        }

    group_body = _body(client, f"/map?group={group_value}&{Q}")
    group_drawn = {i for i, k, _ in _NODE.findall(group_body) if k == "process"}
    expected_group = _process_ids(lambda p: p.group.value == group_value)
    assert group_drawn == expected_group
    assert group_drawn < {n.id for n in GRAPH.by_kind("process")}

    area_body = _body(client, f"/map?area={area_value}&{Q}")
    area_drawn = {i for i, k, _ in _NODE.findall(area_body) if k == "process"}
    expected_area = _process_ids(lambda p: p.area.value == area_value)
    assert area_drawn == expected_area

    bogus_group = _body(client, f"/map?group=not-a-real-group&{Q}")
    assert "not-a-real-group" in bogus_group and 'class="map-notice"' in bogus_group
    bogus_area = _body(client, f"/map?area=not-a-real-area&{Q}")
    assert "not-a-real-area" in bogus_area and 'class="map-notice"' in bogus_area


def test_a_from_equal_to_to_is_a_one_node_path(client: TestClient) -> None:
    process = GRAPH.by_kind("process")[0]
    body = _body(client, f"/map?from={process.id}&to={process.id}&{Q}")
    nodes = {i for i, _, _ in _NODE.findall(body)}
    assert nodes == {process.id}
    assert 'class="map-notice"' not in body


def test_from_and_to_with_no_feeds_path_notices_instead_of_an_empty_drawing(
    client: TestClient,
) -> None:
    """A technique node has no ``feeds`` ties at all (those only run process to
    process), so it can never reach a process by that route -- a real word,
    just not a routable one."""
    technique = GRAPH.by_kind("technique")[0]
    process = GRAPH.by_kind("process")[0]
    body = _body(client, f"/map?from={technique.id}&to={process.id}&{Q}")
    assert "has no feeds path" in body and 'class="map-notice"' in body


_CHIP = re.compile(r'data-dim="(\w+)" value="([^"]+)"')


def _chip_values(body: str, dim: str) -> set[str]:
    return {value for d, value in _CHIP.findall(body) if d == dim}


def test_the_overview_renders_no_chip_it_can_only_empty(client: TestClient) -> None:
    """MP07: the overview draws 49 process nodes and no technique or artifact, so
    a Technique/Artifact kind chip or any Technique-family chip could only hide
    every node on the page -- an unusable chip is never rendered, no message
    needed."""
    body = _body(client, f"/map?{Q}")
    assert _chip_values(body, "kind") == {"process"}
    assert _chip_values(body, "family") == set()
    # The overview's 49 processes still span every group and every area, so
    # those two dimensions stay fully populated.
    assert len(_chip_values(body, "group")) == 5
    assert len(_chip_values(body, "area")) == 10


def test_the_whole_graph_renders_every_chip(client: TestClient) -> None:
    body = _body(client, f"/map?view=all&{Q}")
    assert _chip_values(body, "kind") == {"process", "technique", "artifact"}
    assert len(_chip_values(body, "family")) == 10


def test_show_flow_only_is_absent_when_every_drawn_edge_is_already_feeds(
    client: TestClient,
) -> None:
    """MP07: the overview's 428 edges are all ``feeds``, so the toggle
    (``.map-flow-only .edge:not(.edge-feeds) { display: none; }``) hides
    nothing there -- a no-op control is never rendered."""
    overview_body = _body(client, f"/map?{Q}")
    assert 'id="map-flow-only"' not in overview_body
    whole_graph_body = _body(client, f"/map?view=all&{Q}")
    assert 'id="map-flow-only"' in whole_graph_body


def test_a_one_group_slice_keeps_all_five_bands_as_the_fixed_frame(
    client: TestClient,
) -> None:
    """MP07 narrows the CHIPS to what the slice drew; the bands are not chips.

    The five band captions are the map's fixed frame -- a neighbourhood showing
    three groups draws them where the overview does. Sharing the narrowed chip
    list would shift ``loop.first``/``loop.last``, restripe the shading, and give
    a one-group slice a single band spanning the whole viewbox.
    """
    process = GRAPH.by_kind("process")[0]
    group_value = PROCESS_DEFINITIONS[process.id.partition(":")[2]].process.group.value
    captions = re.compile(r'<text class="band-label"[^>]*>([^<]+)</text>')

    overview = captions.findall(_body(client, f"/map?{Q}"))
    sliced = captions.findall(_body(client, f"/map?group={group_value}&{Q}"))
    assert len(overview) == 5
    assert sliced == overview
    # The chips for that same slice DID narrow -- the two really are separate.
    assert _chip_values(_body(client, f"/map?group={group_value}&{Q}"), "group") == {group_value}
