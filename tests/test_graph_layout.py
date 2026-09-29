"""``pmbok.graph_layout`` places every ``GRAPH`` node on a deterministic grid —
no random, no physics library, no clock. Every guard below is derived from
``LAYOUT`` and ``GRAPH`` themselves, never a restated literal."""

from __future__ import annotations

import re

import pytest

from driftless.pmbok import catalog
from driftless.pmbok import graph_layout
from driftless.pmbok.artifact_definitions import ARTIFACTS, ArtifactDefinition, ArtifactFamily
from driftless.pmbok.graph import GRAPH, Edge, MethodGraph, Node
from driftless.pmbok.graph_layout import LAYOUT, Layout, _build_layout
from driftless.pmbok.graph_views import overview
from driftless.pmbok.model import ProcessGroup

PROCESS_BY_ID = {p.id: p for p in catalog.PROCESSES}


def test_two_builds_are_equal() -> None:
    assert _build_layout() == _build_layout() == LAYOUT


def test_five_bands_by_process_group_top_to_bottom() -> None:
    """A process in an earlier ``ProcessGroup`` (Initiating..Closing) sits in a
    strictly higher (smaller-y) band than one in a later group — the banded
    layout the design pass asked for, derived from the enum's own order."""
    order = {group: index for index, group in enumerate(ProcessGroup)}
    band_y: dict[int, set[int]] = {}
    for node in GRAPH.by_kind("process"):
        key = node.id.partition(":")[2]
        _, y = LAYOUT.positions[node.id]
        band_y.setdefault(order[PROCESS_BY_ID[key].group], set()).add(y)
    present = sorted(band_y)
    assert present, "no process bands found"
    for earlier, later in zip(present, present[1:]):
        assert max(band_y[earlier]) < min(band_y[later]), (
            f"band {earlier} overlaps band {later} vertically"
        )


def test_processes_within_a_band_are_ordered_by_pmbok_number() -> None:
    """Within one band, reading order (top row first, left to right, then the
    next wrapped row) rises with the process's own clause number — ``4.1``
    before ``4.2`` before ``5.1`` — never catalog or name order. A band with
    more processes than one row fits wraps rather than overlapping, so the
    guard reads top-to-bottom-then-left-to-right rather than x alone."""
    by_group: dict[ProcessGroup, list[tuple[tuple[int, ...], tuple[int, int]]]] = {}
    for node in GRAPH.by_kind("process"):
        key = node.id.partition(":")[2]
        process = PROCESS_BY_ID[key]
        x, y = LAYOUT.positions[node.id]
        numeric_id = tuple(int(part) for part in key.split("."))
        by_group.setdefault(process.group, []).append((numeric_id, (y, x)))
    for group, entries in by_group.items():
        entries.sort(key=lambda e: e[0])
        reading_order = [yx for _, yx in entries]
        assert reading_order == sorted(reading_order), (
            f"{group}: processes not laid out in PMBOK-number order"
        )


def test_every_node_has_a_position_inside_the_viewbox() -> None:
    width, height = LAYOUT.viewbox
    assert width > 0 and height > 0
    for node in GRAPH.nodes:
        assert node.id in LAYOUT.positions, f"{node.id} has no position"
        x, y = LAYOUT.positions[node.id]
        assert 0 <= x <= width, f"{node.id} x={x} outside viewbox width {width}"
        assert 0 <= y <= height, f"{node.id} y={y} outside viewbox height {height}"


def test_every_node_has_a_label_box_inside_the_viewbox() -> None:
    width, height = LAYOUT.viewbox
    for node in GRAPH.nodes:
        assert node.id in LAYOUT.label_boxes, f"{node.id} has no label box"
        x, y, w, h = LAYOUT.label_boxes[node.id]
        assert w > 0 and h > 0
        assert 0 <= x and x + w <= width, f"{node.id} box overruns width"
        assert 0 <= y and y + h <= height, f"{node.id} box overruns height"


def _overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def test_no_two_label_boxes_overlap() -> None:
    items = list(LAYOUT.label_boxes.items())
    offenders = []
    for i in range(len(items)):
        id_a, box_a = items[i]
        for j in range(i + 1, len(items)):
            id_b, box_b = items[j]
            if _overlaps(box_a, box_b):
                offenders.append((id_a, id_b))
    assert not offenders, f"overlapping label boxes: {offenders}"


_LABELS = {node.id: node.label for node in GRAPH.nodes}


def _text_box(node_id: str) -> tuple[int, int, int, int]:
    """This node's rendered TEXT extent, centred on ``LAYOUT.positions`` the
    way ``method_map.html`` draws it (``text-anchor="middle"``,
    ``dominant-baseline="central"``) -- estimated with the same
    ``graph_layout._label_width`` glyph-count formula the module itself
    uses, never the small fixed marker box a technique/artifact's
    ``label_boxes`` entry is. A process's own box already IS its label
    width, so this agrees with ``label_boxes`` for processes and only
    differs for the small-dot satellites."""
    x, y = LAYOUT.positions[node_id]
    width = graph_layout._label_width(_LABELS[node_id])
    return x - width // 2, y - graph_layout.LABEL_HEIGHT // 2, width, graph_layout.LABEL_HEIGHT


def test_no_two_label_texts_overlap() -> None:
    """The weak spot in ``test_no_two_label_boxes_overlap`` above: a
    technique/artifact's ``label_boxes`` entry is a small fixed marker (a
    dot/diamond), never its label's own text -- so that test passed while
    every one of the 49 process neighbourhoods' revealed (``.map-narrow``)
    satellite labels visibly overlapped. This checks the TEXT extents
    instead."""
    items = [(node_id, _text_box(node_id)) for node_id in LAYOUT.positions]
    offenders = []
    for i in range(len(items)):
        id_a, box_a = items[i]
        for j in range(i + 1, len(items)):
            id_b, box_b = items[j]
            if _overlaps(box_a, box_b):
                offenders.append((id_a, id_b))
    assert not offenders, f"overlapping label texts: {offenders[:5]} (+{len(offenders) - 5} more)"


def test_no_label_text_overruns_the_viewbox() -> None:
    """The other half of the same finding: a label's TEXT, not just its
    small marker box, must stay inside the viewBox the layout computes --
    16 of them didn't, against the fixed ``CONTENT_WIDTH`` this replaces."""
    width, height = LAYOUT.viewbox
    for node_id in LAYOUT.positions:
        x, y, w, h = _text_box(node_id)
        assert x >= 0 and x + w <= width, f"{node_id} text overruns width"
        assert y >= 0 and y + h <= height, f"{node_id} text overruns height"


def test_edge_paths_start_and_end_on_the_node_boxes_own_edge() -> None:
    """Reshaped from asserting the node CENTRE: an edge that used to start/end
    on the label centre now starts/ends on that label's own box boundary
    (never buried under it) — routing around other boxes needs an exit point
    on the box itself, not its middle."""
    numbers = re.compile(r"-?\d+(?:\.\d+)?")
    for edge in GRAPH.edges:
        path = LAYOUT.edge_paths(edge)
        coords = [float(n) for n in numbers.findall(path)]
        assert len(coords) >= 4
        sx, sy = coords[0], coords[1]
        tx, ty = coords[-2], coords[-1]
        sbx, sby, sbw, sbh = LAYOUT.label_boxes[edge.source]
        tbx, tby, tbw, tbh = LAYOUT.label_boxes[edge.target]
        assert sbx <= sx <= sbx + sbw and sby <= sy <= sby + sbh, (
            f"{edge} path does not start on the source's own box"
        )
        assert tbx <= tx <= tbx + tbw and tby <= ty <= tby + tbh, (
            f"{edge} path does not end on the target's own box"
        )


def test_layout_is_a_frozen_dataclass_instance() -> None:
    assert isinstance(LAYOUT, Layout)


def test_size_is_measured_never_typed() -> None:
    print(f"LAYOUT.viewbox -> {LAYOUT.viewbox}, node count -> {len(LAYOUT.positions)}")
    assert len(LAYOUT.positions) == len(GRAPH.nodes)


#: The graph members no ``used_by``/``reads``/``produces``/``part_of`` edge
#: reaches, named rather than derived so a SECOND cannot appear without this
#: list being edited, and so a member that later gains a real tie has to be
#: removed on purpose. ``development_approach`` and
#: ``performance_measurement_baseline`` left this list once ``COMPONENT_OF``
#: gave them a ``part_of`` tie to ``project_management_plan``; each remaining
#: member is accounted for elsewhere (a disposition or an extension), which is
#: why the totality proof does not call it an orphan -- it simply has no tie
#: to draw.
UNCONNECTED_MEMBERS = ("technique:critical_chain_method",)


def test_the_unconnected_members_are_exactly_the_named_one() -> None:
    """The tray's membership is a contract, not a side effect: derive it from
    ``GRAPH`` and require it to equal the list above, so a second member (or
    the one that grows an edge) fails here instead of appearing silently."""
    assert graph_layout.unconnected_member_ids() == UNCONNECTED_MEMBERS
    derived = tuple(sorted(node.id for node in GRAPH.nodes if not GRAPH.neighbours(node.id)))
    assert derived == tuple(sorted(UNCONNECTED_MEMBERS))


def test_an_artifact_no_process_reaches_goes_to_the_tray_not_a_band(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tray is the home for a member no process names, and until #487 two
    real artifacts (``development_approach``,
    ``performance_measurement_baseline``) proved it for the ARTIFACT half.
    Giving both a ``part_of`` tie emptied that case out of the live data, so
    the branch stopped being exercised by anything -- the rule survived only as
    unexecuted code. Rather than let it rot until a future artifact lands in it
    unnoticed, the case is constructed here: one artifact with no edge of any
    kind, which must sit below every process rather than be parked in Closing.
    The technique half is still covered by live data
    (``technique:critical_chain_method``)."""
    stray = "artifact:stray_untied_kind"
    definition = ArtifactDefinition(
        key="stray_untied_kind",
        display_name="Stray Untied Kind",
        family=next(iter(ArtifactFamily)),
    )
    monkeypatch.setattr(graph_layout, "ARTIFACTS", {**ARTIFACTS, "stray_untied_kind": definition})
    monkeypatch.setattr(
        graph_layout,
        "GRAPH",
        MethodGraph(
            nodes=(*GRAPH.nodes, Node(id=stray, kind="artifact", label="Stray Untied Kind")),
            edges=GRAPH.edges,
        ),
    )
    layout = _build_layout()
    assert stray in layout.positions, "an untied artifact fell out of the layout entirely"
    _sx, stray_y = layout.positions[stray]
    lowest_process_bottom = max(
        layout.label_boxes[node.id][1] + layout.label_boxes[node.id][3]
        for node in GRAPH.by_kind("process")
    )
    assert stray_y > lowest_process_bottom, (
        "an artifact no process reaches was parked in a lifecycle band"
    )


def test_no_unconnected_member_is_parked_in_a_lifecycle_band() -> None:
    """The old layout returned the LAST band for a node with no connections, so
    this one read as belonging to Closing. It does not now: it sits below every
    process in the map, clear of the last band by ``TRAY_GAP``."""
    lowest_process_bottom = max(
        LAYOUT.label_boxes[node.id][1] + LAYOUT.label_boxes[node.id][3]
        for node in GRAPH.by_kind("process")
    )
    for node_id in UNCONNECTED_MEMBERS:
        top = LAYOUT.label_boxes[node_id][1]
        assert top - lowest_process_bottom >= graph_layout.TRAY_GAP, (
            f"{node_id} sits inside a lifecycle band"
        )


def test_the_tray_is_the_bottom_most_row_of_the_map() -> None:
    """``method_map.html`` finds the tray by taking the largest box top in the
    map, and draws its caption just above that. Pin the property that makes
    that reading correct: the tray members share the largest box top, and no
    other node comes near it."""
    tops = {node_id: box[1] for node_id, box in LAYOUT.label_boxes.items()}
    tray_top = max(tops.values())
    assert {node_id for node_id, top in tops.items() if top == tray_top} == set(UNCONNECTED_MEMBERS)
    others = max(top for node_id, top in tops.items() if node_id not in UNCONNECTED_MEMBERS)
    assert tray_top - others >= graph_layout.TRAY_GAP


def test_the_viewbox_grew_to_hold_the_tray() -> None:
    _, height = LAYOUT.viewbox
    for node_id in UNCONNECTED_MEMBERS:
        _, top, _, box_height = LAYOUT.label_boxes[node_id]
        assert top + box_height <= height, f"{node_id} falls outside the viewbox"


def test_a_part_of_member_lands_beside_the_artifact_it_is_part_of() -> None:
    """A component artifact ties to the catalog through its parent, not through
    a process of its own. It inherits the parent's band rather than falling out
    of every band into the tray -- it HAS a tie; the tray is for the members
    that have none."""
    parts = [edge for edge in GRAPH.edges if edge.kind == "part_of"]
    assert parts, "no part_of edge to check"
    for edge in parts:
        assert edge.source not in UNCONNECTED_MEMBERS
        assert LAYOUT.label_boxes[edge.source][1] == LAYOUT.label_boxes[edge.target][1], (
            f"{edge.source} is not on its parent {edge.target}'s row"
        )


def test_a_part_of_child_reserves_its_own_width_in_its_parents_lane() -> None:
    """The lane-colouring walk in ``_stagger_satellite_labels`` skips ``part_of``
    children and forces each onto its parent's lane afterwards. That means the
    child's own text extent has to be folded into the PARENT's reach, or the
    next satellite to the right is coloured as if the child were not there and
    lands on top of it -- which is exactly what happened when
    ``project_management_plan`` gained two components: the child stretched the
    group 570px past the marker the walk measured. Checked as the cause, not as
    the symptom ``test_no_two_label_texts_overlap`` reports."""
    parts = [edge for edge in GRAPH.edges if edge.kind == "part_of"]
    assert parts, "no part_of edge to check"
    for edge in parts:
        child, parent = edge.source, edge.target
        child_x, child_y = LAYOUT.positions[child]
        child_right = child_x + graph_layout._label_width(_LABELS[child]) // 2
        for node_id, (x, y) in LAYOUT.positions.items():
            if node_id in (child, parent) or y != child_y:
                continue
            left = x - graph_layout._label_width(_LABELS[node_id]) // 2
            if x > child_x:
                assert left >= child_right, (
                    f"{node_id} sits on {child}'s lane at x={left} "
                    f"but {child} reaches {child_right}"
                )


def test_focus_view_satellite_labels_do_not_overlap_in_any_process_neighbourhood() -> None:
    """A focus view (``?focus=``, and ``.map-narrow``) reveals every
    technique's/artifact's label at once around the process it neighbours.
    ``graph_layout.focus_layout`` packs a LOCAL layout for that neighbourhood
    alone, each satellite (and any ``feeds`` process neighbour) at its own
    label's width rather than a satellite's small dot/diamond, so two
    revealed labels never overlap -- checked in every one of the 49 process
    neighbourhoods. ``test_no_two_label_boxes_overlap`` above still guards the
    small fixed shape boxes the shared global LAYOUT draws at rest."""
    offenders = []
    for process in catalog.PROCESSES:
        local = graph_layout.focus_layout(f"process:{process.id}")
        items = list(local.label_boxes.items())
        for i in range(len(items)):
            id_a, box_a = items[i]
            for j in range(i + 1, len(items)):
                id_b, box_b = items[j]
                if _overlaps(box_a, box_b):
                    offenders.append((process.id, id_a, id_b))
    assert not offenders, (
        f"overlapping focus-view labels: {offenders[:5]} (+{len(offenders) - 5} more)"
    )


def test_focus_layout_never_changes_the_global_layout() -> None:
    """Computing a per-process local layout must never mutate or drift the
    shared global ``LAYOUT`` -- every other view (the overview, ``?view=all``,
    the committed ``docs/samples`` bundle) draws from ``LAYOUT`` alone and has
    to stay exactly what it was, whatever room a focus view's satellites need."""
    before_viewbox, before_positions = LAYOUT.viewbox, LAYOUT.positions
    for process in catalog.PROCESSES:
        graph_layout.focus_layout(f"process:{process.id}")
    # 1826, not the 1842 this pinned before: giving ``project_management_plan``
    # its two components moved them out of the tray and into its own row, and
    # the widest row narrowed by the tray caption's margin. A drift canary, so
    # the number moves only alongside a deliberate layout change -- never to
    # make a suite green.
    assert LAYOUT.viewbox == before_viewbox == (1826, 2058)
    assert LAYOUT.positions == before_positions
    assert LAYOUT == _build_layout()


def _sample_path(d: str, n: int = 50) -> list[tuple[float, float]]:
    """Every ``d`` this module ever emits is ``M`` then either three ``L``s
    (same-row step) or one ``Q`` (a curve) — walked and sampled by hand
    rather than pulled in an SVG/geometry library for a handful of points."""
    tokens = re.findall(r"[A-Z]|-?\d+(?:\.\d+)?", d)
    points: list[tuple[float, float]] = []
    cur = (0.0, 0.0)
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "M":
            cur = (float(tokens[i + 1]), float(tokens[i + 2]))
            i += 3
        elif token == "L":
            x, y = float(tokens[i + 1]), float(tokens[i + 2])
            for k in range(n + 1):
                f = k / n
                points.append((cur[0] + (x - cur[0]) * f, cur[1] + (y - cur[1]) * f))
            cur = (x, y)
            i += 3
        elif token == "Q":
            mx, my, x, y = (
                float(tokens[i + 1]),
                float(tokens[i + 2]),
                float(tokens[i + 3]),
                float(tokens[i + 4]),
            )
            for k in range(n + 1):
                f = k / n
                g = 1 - f
                points.append(
                    (
                        g * g * cur[0] + 2 * g * f * mx + f * f * x,
                        g * g * cur[1] + 2 * g * f * my + f * f * y,
                    )
                )
            cur = (x, y)
            i += 5
        else:
            i += 1
    return points


def _straight_and_centre_path(x1: int, y1: int, x2: int, y2: int) -> str:
    """The OLD ``edge_paths`` shape (centre-to-centre), reproduced only to
    measure the crossing count it left behind -- never restated as the new
    behaviour."""
    if y1 == y2:
        return f"M {x1} {y1} L {x2} {y2}"
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    return f"M {x1} {y1} Q {mx} {my} {x2} {y2}"


def _point_in_box(point: tuple[float, float], box: tuple[int, int, int, int]) -> bool:
    x, y = point
    bx, by, bw, bh = box
    eps = 0.01
    return bx + eps < x < bx + bw - eps and by + eps < y < by + bh - eps


def _crossing_edges(
    paths: dict[Edge, str], process_boxes: dict[str, tuple[int, int, int, int]]
) -> int:
    crossing = 0
    for edge, path in paths.items():
        points = _sample_path(path)
        for node_id, box in process_boxes.items():
            if node_id in (edge.source, edge.target):
                continue
            if any(_point_in_box(p, box) for p in points):
                crossing += 1
                break
    return crossing


def test_no_overview_same_row_tie_crosses_another_process_box() -> None:
    """The design-pass guard: a same-row ``feeds`` tie used to be a straight
    line running through every box shelved between its endpoints (49 of them,
    measured against the pre-fix shape below). Stepping above/below the row
    clears all of them."""
    view = overview()
    process_boxes = {n.id: LAYOUT.label_boxes[n.id] for n in view.nodes}
    same_row = {
        edge: LAYOUT.edge_paths(edge)
        for edge in view.edges
        if LAYOUT.positions[edge.source][1] == LAYOUT.positions[edge.target][1]
    }
    assert same_row, "no same-row overview tie to check"
    assert _crossing_edges(same_row, process_boxes) == 0


def test_overview_tie_crossings_dropped_from_the_old_centre_to_centre_shape() -> None:
    """Measures the whole overview, same-row and band-crossing ties together,
    against the shape this PR replaces -- a real reduction, not just the
    same-row case the previous guard proves outright."""
    view = overview()
    process_boxes = {n.id: LAYOUT.label_boxes[n.id] for n in view.nodes}
    old_paths = {
        edge: _straight_and_centre_path(
            *LAYOUT.positions[edge.source], *LAYOUT.positions[edge.target]
        )
        for edge in view.edges
    }
    new_paths = {edge: LAYOUT.edge_paths(edge) for edge in view.edges}
    old_crossings = _crossing_edges(old_paths, process_boxes)
    new_crossings = _crossing_edges(new_paths, process_boxes)
    print(f"overview edge crossings -> old {old_crossings}, new {new_crossings}")
    assert new_crossings < old_crossings


def test_overview_edge_paths_are_deterministic() -> None:
    rebuilt = _build_layout()
    view = overview()
    for edge in view.edges:
        assert rebuilt.edge_paths(edge) == LAYOUT.edge_paths(edge)
