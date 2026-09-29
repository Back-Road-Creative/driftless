"""Views onto ``graph.GRAPH``: a process-first OVERVIEW and a per-node
NEIGHBOURHOOD, so a page can show a readable slice instead of every node and
every edge at once.

Pure, deterministic and I/O-free, the same contract ``graph_layout`` keeps.
Every node and every tie here is an object taken straight out of ``GRAPH`` —
nothing is copied, restated or re-derived from the catalog, so a view can never
disagree with the graph it is a slice of. Ordering is fixed: the overview walks
the five ``ProcessGroup``s in the enum's own lifecycle order and, within a
group, PMBOK-number order (``"4.2"`` before ``"4.10"``, numerically, not as
text); every other view keeps ``GRAPH``'s own node order. Edges are always and
only those with BOTH ends inside the view's own node set, in ``GRAPH``'s edge
order — an edge to a node the view does not show would be a dangling line.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from driftless.pmbok import catalog
from driftless.pmbok.graph import GRAPH, Edge, Node
from driftless.pmbok.model import ProcessGroup

_GROUP_ORDER: dict[ProcessGroup, int] = {group: i for i, group in enumerate(ProcessGroup)}
_PROCESS_BY_ID = {p.id: p for p in catalog.PROCESSES}


@dataclass(frozen=True)
class ViewCounts:
    """A view's size against the whole graph's: the numbers a caller needs to
    say "N of TOTAL nodes; M relevant ties". The sentence is the caller's —
    this carries only the four numbers, so no wording is frozen here."""

    nodes: int
    edges: int
    total_nodes: int
    total_edges: int


@dataclass(frozen=True)
class GraphView:
    """One readable slice of ``GRAPH``: its nodes, the ties internal to them,
    and the node the slice was built around (``None`` for the overview)."""

    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    focus: str | None = None

    def counts(self) -> ViewCounts:
        """This view measured against ``GRAPH.size()`` — measured, never restated."""
        total_nodes, total_edges = GRAPH.size()
        return ViewCounts(
            nodes=len(self.nodes),
            edges=len(self.edges),
            total_nodes=total_nodes,
            total_edges=total_edges,
        )


def _internal_edges(node_ids: AbstractSet[str]) -> tuple[Edge, ...]:
    """Every ``GRAPH`` edge with both ends inside ``node_ids``, in graph order."""
    return tuple(e for e in GRAPH.edges if e.source in node_ids and e.target in node_ids)


def _lifecycle_key(process_id: str) -> tuple[int, tuple[int, ...]]:
    process = _PROCESS_BY_ID[process_id]
    return (
        _GROUP_ORDER[process.group],
        tuple(int(part) for part in process.id.split(".")),
    )


def overview() -> GraphView:
    """Every process node, in lifecycle order, with the ``feeds`` ties between
    them — the whole method at one altitude, with techniques and artifacts left
    to ``neighbourhood``."""
    nodes = tuple(
        sorted(GRAPH.by_kind("process"), key=lambda n: _lifecycle_key(n.id.split(":", 1)[1]))
    )
    return GraphView(nodes=nodes, edges=_internal_edges({n.id for n in nodes}))


def neighbourhood(node_id: str) -> GraphView:
    """The ego network of ``node_id``: the node itself, its direct neighbours
    across every edge kind, and only the ties internal to that set. A node the
    catalog leaves unconnected returns itself with zero ties. An unknown id is
    a ``KeyError`` rather than an empty view, which would read as "connected to
    nothing" for what is really a typo."""
    if node_id not in {n.id for n in GRAPH.nodes}:
        raise KeyError(node_id)
    ids = {node_id, *GRAPH.neighbours(node_id)}
    return GraphView(
        nodes=tuple(n for n in GRAPH.nodes if n.id in ids),
        edges=_internal_edges(ids),
        focus=node_id,
    )
