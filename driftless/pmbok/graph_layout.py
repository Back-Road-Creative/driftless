"""``LAYOUT``: a deterministic 2-D placement for every ``graph.GRAPH`` node.

No randomness, no physics/force-directed library and no clock: coordinates
are integers in a fixed viewBox, computed once at import from the frozen
``GRAPH`` — the same pattern as ``web/techniques.py``'s ``BY_SLUG``. Two
builds are always equal.

Five horizontal BANDS, one per ``ProcessGroup`` (Initiating..Closing, the
enum's own lifecycle order) top to bottom. Within a band, processes are
shelf-packed left to right in PMBOK-number order (``"4.1"`` before ``"4.2"``
before ``"5.1"``), wrapping to a new row rather than overlapping — the same
shelf-packing a text reader already knows from word wrap.

Every technique and artifact is a SATELLITE of the processes that use it —
``used_by``/``reads``/``produces`` edges off ``GRAPH``, never a second list —
placed in the band its connected processes are earliest in (a technique used
across several groups still needs exactly one home). A member no such edge
reaches has NO band: it goes in its own TRAY below all five, because the old
"fall back to the last band" rule made the map assert that four members
belong to Closing when no edge and no catalog fact says so.

Within a band, artifacts pack first (the inner
row, closer to the processes that read/produce them) then techniques (the
outer row), each row ordered by the x centroid of ITS OWN connected
processes so a satellite lands near the process(es) that reach it rather
than in family or alphabetical order. Splitting an over-full row into more
rows is the answer to overlap, not shrinking a label below ``GLYPH_WIDTH``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from driftless.pmbok import catalog
from driftless.pmbok.artifact_definitions import ARTIFACTS, ArtifactFamily
from driftless.pmbok.definitions import TECHNIQUES, TechniqueFamily
from driftless.pmbok.graph import GRAPH, Edge
from driftless.pmbok.model import Process, ProcessGroup

#: Estimated pixels per glyph — a named minimum, never shrunk to force a fit.
#: 8, not a tighter estimate: the rendered `--fs-sm` label (map.css) measured
#: wider than 7px/glyph for the longest process names ("Plan Communications
#: Management", "Perform Quantitative Risk Analysis"), overflowing their own
#: box at 7 — verified by screenshot, not assumed.
GLYPH_WIDTH = 8
#: Padding added to a label's raw glyph width, each side folded in together.
LABEL_PAD = 14
LABEL_HEIGHT = 18
#: Gap between adjacent shelf items / rows.
H_GAP = 16
V_GAP = 16
#: Extra gap inserted between two families packed into the same shelf row.
FAMILY_GAP = 28
#: Gap between a band's process row and its satellite rows, and between bands.
BAND_GAP = 32
#: Clear space between the last lifecycle band and the unconnected-member TRAY:
#: wide enough that the tray reads as a separate thing rather than one more
#: satellite row of Closing, and wide enough for the caption ``method_map.html``
#: draws in it. Bigger than ``BAND_GAP`` on purpose -- the gap IS the statement
#: that these members are outside the lifecycle, so it must not read as the gap
#: between two bands.
TRAY_GAP = 64
MARGIN = 24
#: A same-row edge's vertical step above/below its own row, clearing every
#: box shelved between its endpoints. Kept well under ``V_GAP`` (the gap to
#: the next row) so the step can never land inside a neighbouring row.
ROW_ARC_CLEARANCE = 8
#: Fixed row height every shelf-packed node takes (process, technique, artifact alike).
BAND_ROW_HEIGHT = LABEL_HEIGHT + 8
#: A technique/artifact satellite's fixed footprint: a small dot/diamond, never
#: sized off its own label — the label stays hidden at rest (shown on
#: hover/focus/narrow-filter by map.css/map.js), so reserving full text width
#: for it would pack every satellite row as loosely as the process grid it is
#: meant to sit *inside*.
SATELLITE_SIZE = LABEL_HEIGHT + 6

_GROUPS: tuple[ProcessGroup, ...] = tuple(ProcessGroup)
_GROUP_ORDER: Mapping[ProcessGroup, int] = {group: index for index, group in enumerate(_GROUPS)}
_PROCESS_BY_ID: Mapping[str, Process] = {p.id: p for p in catalog.PROCESSES}
_ARTIFACT_FAMILY_ORDER: Mapping[ArtifactFamily, int] = {
    family: index for index, family in enumerate(ArtifactFamily)
}
_TECHNIQUE_FAMILY_ORDER: Mapping[TechniqueFamily, int] = {
    family: index for index, family in enumerate(TechniqueFamily)
}


def _label_width(label: str) -> int:
    """This label's estimated box width: glyph count times a fixed glyph
    width, plus padding — never measured text, so it is deterministic."""
    return len(label) * GLYPH_WIDTH + LABEL_PAD


@dataclass(frozen=True)
class Layout:
    """The whole method graph's placement: a fixed viewBox, one position and
    one label box per node id."""

    viewbox: tuple[int, int]
    positions: Mapping[str, tuple[int, int]]
    label_boxes: Mapping[str, tuple[int, int, int, int]]

    def edge_paths(self, edge: Edge) -> str:
        """This edge's SVG path ``d``, starting/ending on the two nodes'
        BOX EDGES rather than their centres, so a path never begins or ends
        buried under a label.

        Same-row endpoints (a straight ``L`` used to run right through every
        box shelved between them) instead step above the row for a
        left-to-right tie or below it for a right-to-left one — a fixed,
        small clearance that stays inside the row's own gap to its neighbour
        so it can never reach into an adjacent row, and holds constant while
        it crosses the row, so it clears every box in between regardless of
        how many there are. Endpoints on different rows exit/enter at the
        box's top or bottom edge (whichever faces the other node) joined by
        one smooth quadratic curve."""
        x1, y1 = self.positions[edge.source]
        x2, y2 = self.positions[edge.target]
        sbx, sby, sbw, sbh = self.label_boxes[edge.source]
        tbx, tby, tbw, tbh = self.label_boxes[edge.target]
        if y1 == y2:
            if x1 <= x2:
                sx, sy = sbx + sbw, y1
                tx, ty = tbx, y2
                step_y = sby - ROW_ARC_CLEARANCE
            else:
                sx, sy = sbx, y1
                tx, ty = tbx + tbw, y2
                step_y = sby + sbh + ROW_ARC_CLEARANCE
            return f"M {sx} {sy} L {sx} {step_y} L {tx} {step_y} L {tx} {ty}"
        if y1 < y2:
            sx, sy = x1, sby + sbh
            tx, ty = x2, tby
        else:
            sx, sy = x1, sby
            tx, ty = x2, tby + tbh
        mx, my = (sx + tx) / 2, (sy + ty) / 2
        return f"M {sx} {sy} Q {mx} {my} {tx} {ty}"


def _shelf_pack(
    entries: Sequence[tuple[str, int, str]], max_width: int
) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int, int, int]], int]:
    """Shelf-packs ``entries`` (node id, box width, a family/group value used
    only to insert a small extra gap on change — never to re-sort) left to
    right from ``(MARGIN, 0)``, wrapping to a new row rather than overlapping.
    Returns ``(positions, label_boxes, block_height)``, both relative to a
    band-local origin of ``(0, 0)``."""
    positions: dict[str, tuple[int, int]] = {}
    boxes: dict[str, tuple[int, int, int, int]] = {}
    x = MARGIN
    y = 0
    prev_family: str | None = None
    for node_id, width, family in entries:
        if prev_family is not None and family != prev_family and x > MARGIN:
            x += FAMILY_GAP - H_GAP
        if x > MARGIN and x + width > MARGIN + max_width:
            x = MARGIN
            y += BAND_ROW_HEIGHT + V_GAP
        positions[node_id] = (x + width // 2, y + BAND_ROW_HEIGHT // 2)
        boxes[node_id] = (x, y, width, BAND_ROW_HEIGHT)
        x += width + H_GAP
        prev_family = family
    return positions, boxes, y + BAND_ROW_HEIGHT


#: Vertical step between two "lanes" of staggered satellite labels -- one
#: ``LABEL_HEIGHT`` clears the lane above's text exactly (see
#: ``_stagger_satellite_labels``), never less.
LANE_STEP = LABEL_HEIGHT


def _stagger_satellite_labels(
    positions: Mapping[str, tuple[int, int]],
    boxes: Mapping[str, tuple[int, int, int, int]],
    labels: Mapping[str, str],
    same_row_as: Mapping[str, str] = {},
) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int, int, int]], int]:
    """A shelf-packed satellite row spaces its small dot/diamond MARKERS at
    ``SATELLITE_SIZE`` pitch, far narrower than a label's own estimated text
    width -- widening every marker to its label's width would blow up a busy
    band far more than a reader gains (a tradeoff spelled out in the PR that
    added this function), so instead each row's labels are staggered onto
    alternating vertical "lanes". Walked left to right (the row's own
    ``_shelf_pack`` order) within each of the shelf's own physical rows,
    each label goes in the lowest lane whose last-placed label's estimated
    text box does not reach it -- classic interval-graph colouring,
    deterministic because that walk order is. A row's busiest lane pushes
    every row BELOW it down by that same amount, so a lane never encroaches
    on the next physical row's markers.

    ``same_row_as`` (child id -> parent id, e.g. a ``part_of`` tie) forces
    the child onto whatever lane its parent lands on -- the two must stay
    on the same row, a contract this function does not otherwise know
    about -- rather than being coloured independently.

    Returns ``(positions, boxes, extra_height)``: only Y moves, a label's
    marker with it so the two never detach, and ``extra_height`` is the
    total the caller's block grows by."""
    rows: dict[int, list[str]] = {}
    children_of: dict[str, list[str]] = {}
    for child_id, parent_id in same_row_as.items():
        children_of.setdefault(parent_id, []).append(child_id)
    for node_id, (_x, base_y) in positions.items():
        if node_id not in same_row_as:
            rows.setdefault(base_y, []).append(node_id)

    def _span(node_id: str) -> tuple[int, int]:
        """This node's text extent, WIDENED to cover every child forced onto
        its lane below. A child is skipped by the walk, so its own width has
        to be reserved here or the next node right is coloured against the
        parent's marker alone and lands on top of the child."""
        edges = []
        for member in (node_id, *children_of.get(node_id, ())):
            member_x, _member_y = positions[member]
            half = _label_width(labels[member]) // 2
            edges.append((member_x - half, member_x + half))
        return min(left for left, _r in edges), max(right for _l, right in edges)

    new_positions = dict(positions)
    new_boxes = dict(boxes)
    cumulative_shift = 0
    for base_y in sorted(rows):
        node_ids = sorted(rows[base_y], key=lambda nid: positions[nid][0])
        lane_reach: list[int] = []
        lane_of: dict[str, int] = {}
        for node_id in node_ids:
            left, right = _span(node_id)
            lane = next((i for i, reach in enumerate(lane_reach) if left >= reach), len(lane_reach))
            if lane == len(lane_reach):
                lane_reach.append(right)
            else:
                lane_reach[lane] = right
            lane_of[node_id] = lane
        for node_id in node_ids:
            shift = cumulative_shift + lane_of[node_id] * LANE_STEP
            px, py = new_positions[node_id]
            new_positions[node_id] = (px, py + shift)
            bx, by, bw, bh = new_boxes[node_id]
            new_boxes[node_id] = (bx, by + shift, bw, bh)
        cumulative_shift += max(lane_of.values(), default=0) * LANE_STEP
    for child_id, parent_id in same_row_as.items():
        if child_id in new_positions and parent_id in new_positions:
            px, py = new_positions[parent_id]
            cx, _cy = new_positions[child_id]
            new_positions[child_id] = (cx, py)
            _bx, by, bw, bh = new_boxes[parent_id]
            cbx, _cby, cbw, cbh = new_boxes[child_id]
            new_boxes[child_id] = (cbx, by, cbw, cbh)
    return new_positions, new_boxes, cumulative_shift


def _connected_processes() -> dict[str, set[str]]:
    """Every technique/artifact node id -> the ``process:...`` ids it ties to,
    off ``GRAPH.edges`` alone: ``used_by`` (technique), ``reads`` and
    ``produces`` (artifact, either edge direction), plus ``part_of`` -- a
    component artifact inherits the processes of the artifact it is part of, so
    it lands beside its own parent rather than nowhere. Without that, the one
    ``part_of`` member in the catalog (the work breakdown structure, part of
    the scope baseline) reads as having no home at all, which is false: it has
    a tie, just not a process's."""
    connected: dict[str, set[str]] = {}
    for edge in GRAPH.edges:
        if edge.kind == "used_by" or edge.kind == "reads":
            connected.setdefault(edge.source, set()).add(edge.target)
        elif edge.kind == "produces":
            connected.setdefault(edge.target, set()).add(edge.source)
    for edge in GRAPH.edges:
        if edge.kind == "part_of":
            connected.setdefault(edge.source, set()).update(connected.get(edge.target, set()))
    return connected


#: Every band and every satellite row wraps within this width. Fixed rather
#: than "the widest band in one row" (what the biggest ``ProcessGroup``,
#: Planning at 24 processes, would need): that reads as one row 4000+px wide
#: and, once a browser scales the SVG's intrinsic ratio down to a legible
#: on-screen width, squashes every band's HEIGHT down with it — the map read
#: as a thin illegible smear. 1600px keeps every band (Planning included)
#: wrapping onto several rows instead, so the whole map is close to the
#: on-screen aspect a reader actually gets, not the width the busiest single
#: band alone would want.
CONTENT_WIDTH = 1600


def _build_layout() -> Layout:
    content_width = CONTENT_WIDTH
    connected = _connected_processes()
    labels = {node.id: node.label for node in GRAPH.nodes}

    # Pass 1: shelf-pack every band's processes, relative to a band-local
    # (0, 0) origin. Absolute x is already final here — only y is shifted
    # later — so a satellite's centroid can be computed off it immediately.
    process_positions: dict[str, tuple[int, int]] = {}
    process_boxes: dict[str, tuple[int, int, int, int]] = {}
    process_block_height: dict[ProcessGroup, int] = {}
    for group in _GROUPS:
        processes = sorted(
            (p for p in catalog.PROCESSES if p.group == group),
            key=lambda p: tuple(int(part) for part in p.id.split(".")),
        )
        entries = [(f"process:{p.id}", _label_width(p.name), p.area.value) for p in processes]
        row_positions, row_boxes, height = _shelf_pack(entries, content_width)
        process_positions.update(row_positions)
        process_boxes.update(row_boxes)
        process_block_height[group] = height if entries else 0

    def centroid_x(process_ids: set[str]) -> float:
        xs = [process_positions[pid][0] for pid in process_ids if pid in process_positions]
        return sum(xs) / len(xs) if xs else float("inf")

    def primary_group(node_id: str) -> ProcessGroup | None:
        """The earliest band any process reaching this node sits in, or ``None``
        when no process reaches it at all -- a tray member, never a band's."""
        process_ids = connected.get(node_id, set())
        if not process_ids:
            return None
        return min(
            (_PROCESS_BY_ID[pid.partition(":")[2]].group for pid in process_ids),
            key=lambda group: _GROUP_ORDER[group],
        )

    tray_entries: list[tuple[int, str, str]] = []
    artifacts_by_group: dict[ProcessGroup, list[tuple[float, int, str, str, str]]] = {
        g: [] for g in _GROUPS
    }
    for artifact_key, artifact_definition in ARTIFACTS.items():
        node_id = f"artifact:{artifact_key}"
        home = primary_group(node_id)
        if home is None:
            tray_entries.append((0, node_id, artifact_definition.family.value))
            continue
        artifacts_by_group[home].append(
            (
                centroid_x(connected.get(node_id, set())),
                _ARTIFACT_FAMILY_ORDER[artifact_definition.family],
                artifact_definition.display_name,
                node_id,
                artifact_definition.family.value,
            )
        )

    techniques_by_group: dict[ProcessGroup, list[tuple[float, int, str, str, str]]] = {
        g: [] for g in _GROUPS
    }
    for technique_key, technique_definition in TECHNIQUES.items():
        node_id = f"technique:{technique_key}"
        home = primary_group(node_id)
        if home is None:
            tray_entries.append((1, node_id, technique_definition.family.value))
            continue
        techniques_by_group[home].append(
            (
                centroid_x(connected.get(node_id, set())),
                _TECHNIQUE_FAMILY_ORDER[technique_definition.family],
                technique_definition.display_name,
                node_id,
                technique_definition.family.value,
            )
        )

    positions: dict[str, tuple[int, int]] = {}
    label_boxes: dict[str, tuple[int, int, int, int]] = {}
    max_right = MARGIN + content_width

    # A part_of child stays on its parent artifact's row by contract (see
    # ``test_a_part_of_member_lands_beside_the_artifact_it_is_part_of``) --
    # staggering colours each satellite independently, so a child must be
    # told to follow its parent's lane rather than choosing its own.
    part_of_parent = {edge.source: edge.target for edge in GRAPH.edges if edge.kind == "part_of"}
    children_by_parent: dict[str, list[str]] = {}
    for child_id, parent_id in part_of_parent.items():
        children_by_parent.setdefault(parent_id, []).append(child_id)

    def _place_relative(
        rel_positions: Mapping[str, tuple[int, int]],
        rel_boxes: Mapping[str, tuple[int, int, int, int]],
        top_y: int,
    ) -> None:
        for node_id, (x, y) in rel_positions.items():
            positions[node_id] = (x, y + top_y)
        for node_id, (x, y, w, h) in rel_boxes.items():
            label_boxes[node_id] = (x, y + top_y, w, h)

    y = MARGIN
    for group in _GROUPS:
        band_process_ids = {nid for nid in process_positions if _row_group(nid) == group}
        _place_relative(
            {nid: process_positions[nid] for nid in band_process_ids},
            {nid: process_boxes[nid] for nid in band_process_ids},
            y,
        )
        y += process_block_height[group]

        group_ids = {node_id for _, _, _, node_id, _ in artifacts_by_group[group]}
        # A part_of PARENT and its child must share a row (the contract
        # ``test_a_part_of_member_lands_beside_the_artifact_it_is_part_of``
        # pins) yet never let their TEXT overlap, which a shared marker
        # pitch cannot guarantee. Fold each child into ONE shelf entry sized
        # to fit both labels plus a gap -- exactly what shelf-packing
        # already guarantees for every other row -- then split it back into
        # the parent's and child's own small marker positions below.
        group_children = {
            parent_id: [c for c in children if c in group_ids]
            for parent_id, children in children_by_parent.items()
            if parent_id in group_ids
        }
        folded_children = {c for cs in group_children.values() for c in cs}
        artifact_entries = []
        for _, _, display_name, node_id, family in sorted(artifacts_by_group[group]):
            if node_id in folded_children:
                continue
            children = group_children.get(node_id, [])
            if children:
                width = _label_width(display_name) + sum(
                    H_GAP + _label_width(labels[c]) for c in children
                )
            else:
                width = SATELLITE_SIZE
            artifact_entries.append((node_id, width, family))
        if artifact_entries:
            y += BAND_GAP
            art_positions, art_boxes, art_height = _shelf_pack(artifact_entries, content_width)
            for parent_id, children in group_children.items():
                if not children or parent_id not in art_positions:
                    continue
                px, py = art_positions[parent_id]
                bx, by, _bw, bh = art_boxes[parent_id]
                left = bx
                parent_width = _label_width(labels[parent_id])
                parent_x = left + parent_width // 2
                art_positions[parent_id] = (parent_x, py)
                art_boxes[parent_id] = (parent_x - SATELLITE_SIZE // 2, by, SATELLITE_SIZE, bh)
                cursor = left + parent_width + H_GAP
                for child_id in children:
                    child_width = _label_width(labels[child_id])
                    child_x = cursor + child_width // 2
                    art_positions[child_id] = (child_x, py)
                    art_boxes[child_id] = (child_x - SATELLITE_SIZE // 2, by, SATELLITE_SIZE, bh)
                    cursor += child_width + H_GAP
            art_positions, art_boxes, extra = _stagger_satellite_labels(
                art_positions, art_boxes, labels, part_of_parent
            )
            _place_relative(art_positions, art_boxes, y)
            y += art_height + extra

        technique_entries = [
            (node_id, SATELLITE_SIZE, family)
            for _, _, _, node_id, family in sorted(techniques_by_group[group])
        ]
        if technique_entries:
            y += BAND_GAP
            tech_positions, tech_boxes, tech_height = _shelf_pack(technique_entries, content_width)
            tech_positions, tech_boxes, extra = _stagger_satellite_labels(
                tech_positions, tech_boxes, labels
            )
            _place_relative(tech_positions, tech_boxes, y)
            y += tech_height + extra

        y += BAND_GAP
    y -= BAND_GAP

    # The TRAY: members no edge reaches, on one shelf-packed row below every
    # band, sorted (artifacts, then techniques, each by node id) so the row is
    # byte-identical build to build. `method_map.html` finds it by taking the
    # largest label-box top in the map and captions it there, which TRAY_GAP is
    # what makes unambiguous -- see tests/test_graph_layout.py.
    if tray_entries:
        y += TRAY_GAP
        # Packed at the label's OWN width, never ``SATELLITE_SIZE`` + a
        # stagger: the tray is contractually a single shared row (see
        # ``test_the_tray_is_the_bottom_most_row_of_the_map``), and with only
        # ``UNCONNECTED_MEMBERS``-few entries, spacing at full label width
        # keeps them non-overlapping without ever needing a second row.
        entries = [
            (node_id, _label_width(labels[node_id]), family)
            for _, node_id, family in sorted(tray_entries)
        ]
        tray_positions, tray_boxes, tray_height = _shelf_pack(entries, content_width)
        _place_relative(tray_positions, tray_boxes, y)
        y += tray_height

    # A satellite's revealed TEXT (under `.map-narrow`) is far wider than its
    # small marker box, and can reach past either edge of a row packed at
    # marker pitch -- the fixed `content_width`-based `max_right` above never
    # accounted for it. Grow the viewBox to the widest/leftmost text edge
    # actually reached, translating everything right first if any label's
    # text would otherwise start left of x=0.
    text_left = min(x - _label_width(labels[nid]) // 2 for nid, (x, _y) in positions.items())
    text_right = max(x + _label_width(labels[nid]) // 2 for nid, (x, _y) in positions.items())
    shift = max(0, MARGIN - text_left)
    if shift:
        positions = {nid: (x + shift, y_) for nid, (x, y_) in positions.items()}
        label_boxes = {nid: (x + shift, y_, w, h) for nid, (x, y_, w, h) in label_boxes.items()}
    width = max(max_right + MARGIN, text_right + shift + MARGIN)
    viewbox = (width, y + MARGIN)
    return Layout(viewbox=viewbox, positions=positions, label_boxes=label_boxes)


#: A focus view's own satellite/neighbour-process row width -- narrow enough
#: that the shelf reads as belonging to one process, not the whole map's
#: 1600px ``CONTENT_WIDTH``.
FOCUS_CONTENT_WIDTH = 640


def focus_layout(node_id: str) -> Layout:
    """A wholly LOCAL layout for one node's neighbourhood -- what ``?focus=``
    draws instead of the shared global ``LAYOUT``. The focused node anchors
    a fixed local origin; every process tied to it, then every
    technique/artifact tied to it, shelf-packs in its own row below, each
    slot at ITS OWN label's width (``_label_width``) rather than a satellite's
    small dot/diamond -- exactly the room a ``.map-narrow``/``?focus=`` view
    needs once it reveals every label at once. Pure and deterministic (same
    ``GRAPH`` neighbours in, same small layout out) and independent of
    ``LAYOUT``, which a focus view never touches -- widening ONE
    neighbourhood's satellites no longer has to widen the whole map's
    ``viewBox`` the way it did before this function existed."""
    labels = {node.id: node.label for node in GRAPH.nodes}
    anchor_width = _label_width(labels[node_id])
    positions: dict[str, tuple[int, int]] = {
        node_id: (MARGIN + anchor_width // 2, MARGIN + BAND_ROW_HEIGHT // 2)
    }
    label_boxes: dict[str, tuple[int, int, int, int]] = {
        node_id: (MARGIN, MARGIN, anchor_width, BAND_ROW_HEIGHT)
    }
    neighbour_ids = GRAPH.neighbours(node_id)
    process_neighbours = sorted(nid for nid in neighbour_ids if nid.partition(":")[0] == "process")
    satellite_ids = sorted(nid for nid in neighbour_ids if nid.partition(":")[0] != "process")

    y = MARGIN + BAND_ROW_HEIGHT
    max_right = MARGIN + anchor_width
    for row_ids in (process_neighbours, satellite_ids):
        if not row_ids:
            continue
        y += BAND_GAP
        entries = [(nid, _label_width(labels[nid]), nid.partition(":")[0]) for nid in row_ids]
        row_positions, row_boxes, row_height = _shelf_pack(entries, FOCUS_CONTENT_WIDTH)
        for nid, (x, ry) in row_positions.items():
            positions[nid] = (x, ry + y)
        for nid, (x, ry, w, h) in row_boxes.items():
            label_boxes[nid] = (x, ry + y, w, h)
            max_right = max(max_right, x + w)
        y += row_height

    return Layout(
        viewbox=(max_right + MARGIN, y + MARGIN), positions=positions, label_boxes=label_boxes
    )


def unconnected_member_ids() -> tuple[str, ...]:
    """Every ``GRAPH`` member no tie reaches at all, sorted -- the tray's
    membership. Each is accounted for elsewhere (a disposition or an
    extension), which is why the totality proof does not call it an orphan; it
    simply has nothing to draw a line to, so it gets no lifecycle band."""
    return tuple(sorted(node.id for node in GRAPH.nodes if not GRAPH.neighbours(node.id)))


def _row_group(node_id: str) -> ProcessGroup:
    """The ``ProcessGroup`` a ``process:...`` node id belongs to."""
    return _PROCESS_BY_ID[node_id.partition(":")[2]].group


#: The whole method graph's layout, built once at import.
LAYOUT: Layout = _build_layout()
