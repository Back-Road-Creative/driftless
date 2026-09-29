"""The method graph: every process, technique and artifact as one graph, its
edges derived entirely from ``catalog.PROCESSES`` rather than authored twice.
A node's ``id`` is kind-prefixed: ``"process:7.2"``, ``"technique:…"``,
``"artifact:…"``. Edges: ``artifact -reads-> process`` and
``process -produces-> artifact`` (``optional`` from ``optional_outputs``) off
a process's inputs/outputs, ``technique -used_by-> process`` off its
tools_techniques, a DERIVED ``process -feeds-> process`` wherever one
process's output is another's input, and ``artifact -part_of-> artifact`` off
``artifacts.COMPONENT_OF`` for a kind that is a named component of another
(the WBS inside the scope baseline) rather than a process's own output. Pure
and clock-free: ``GRAPH``, built once at import, is equal to a fresh
``_build()`` every time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from driftless.naming import humanize
from driftless.pmbok import catalog
from driftless.pmbok.artifacts import ARTIFACT_KINDS, COMPONENT_OF
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.tt import TT_CATALOG

NodeKind = Literal["process", "technique", "artifact"]
EdgeKind = Literal["reads", "produces", "used_by", "feeds", "part_of"]


@dataclass(frozen=True)
class Node:
    """One graph node: a process, a technique or an artifact kind."""

    id: str
    kind: NodeKind
    label: str


@dataclass(frozen=True)
class Edge:
    """One directed edge. ``optional`` is true on a ``produces`` edge for a
    process's declared conditional output, and on a ``feeds`` edge only when
    EVERY artifact behind it is one of the producer's optional outputs — if
    any one artifact linking the pair is a required output, the edge is
    certain."""

    source: str
    target: str
    kind: EdgeKind
    optional: bool = False


@dataclass(frozen=True)
class MethodGraph:
    """The whole method graph: nodes and edges, both immutable tuples."""

    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]

    def neighbours(self, node_id: str) -> tuple[str, ...]:
        """Every node id connected to ``node_id``, either direction, sorted.
        Empty means an orphan node."""
        ids = {e.target for e in self.edges if e.source == node_id}
        ids |= {e.source for e in self.edges if e.target == node_id}
        return tuple(sorted(ids))

    def by_kind(self, kind: NodeKind) -> tuple[Node, ...]:
        """Every node of ``kind``, in the graph's own node order."""
        return tuple(n for n in self.nodes if n.kind == kind)

    def size(self) -> tuple[int, int]:
        """``(node_count, edge_count)`` — measured, never restated elsewhere."""
        return len(self.nodes), len(self.edges)

    def to_dict(self) -> dict[str, list[dict[str, Any]]]:
        """A tiny JSON-serialisable shape, for a later ``/map/graph.json`` route."""
        return {
            "nodes": [{"id": n.id, "kind": n.kind, "label": n.label} for n in self.nodes],
            "edges": [
                {"source": e.source, "target": e.target, "kind": e.kind, "optional": e.optional}
                for e in self.edges
            ],
        }


def _build() -> MethodGraph:
    nodes: list[Node] = []
    nodes += [
        Node(id=f"artifact:{k}", kind="artifact", label=humanize(k)) for k in sorted(ARTIFACT_KINDS)
    ]
    nodes += [
        Node(id=f"technique:{k}", kind="technique", label=TECHNIQUES[k].display_name)
        for k in sorted(TT_CATALOG)
    ]
    nodes += [Node(id=f"process:{p.id}", kind="process", label=p.name) for p in catalog.PROCESSES]

    edges: list[Edge] = []
    for process in catalog.PROCESSES:
        pid = f"process:{process.id}"
        edges += [Edge(source=f"artifact:{a}", target=pid, kind="reads") for a in process.inputs]
        edges += [
            Edge(
                source=pid,
                target=f"artifact:{a}",
                kind="produces",
                optional=a in process.optional_outputs,
            )
            for a in process.outputs
        ]
        edges += [
            Edge(source=f"technique:{t}", target=pid, kind="used_by")
            for t in process.tools_techniques
        ]

    produced_by: dict[str, set[str]] = {}
    optional_by: dict[str, set[str]] = {}
    for process in catalog.PROCESSES:
        for artifact_key in process.outputs:
            produced_by.setdefault(artifact_key, set()).add(process.id)
            if artifact_key in process.optional_outputs:
                optional_by.setdefault(artifact_key, set()).add(process.id)

    feeds: dict[tuple[str, str], bool] = {}
    for process in catalog.PROCESSES:
        for artifact_key in process.inputs:
            for producer_id in produced_by.get(artifact_key, ()):
                if producer_id != process.id:
                    pair = (producer_id, process.id)
                    is_optional = producer_id in optional_by.get(artifact_key, ())
                    feeds[pair] = feeds.get(pair, True) and is_optional
    edges += [
        Edge(source=f"process:{a}", target=f"process:{b}", kind="feeds", optional=optional)
        for (a, b), optional in sorted(feeds.items())
    ]

    edges += [
        Edge(source=f"artifact:{part}", target=f"artifact:{whole}", kind="part_of")
        for part, whole in sorted(COMPONENT_OF.items())
    ]

    return MethodGraph(nodes=tuple(nodes), edges=tuple(edges))


#: The whole method graph, built once at import.
GRAPH: MethodGraph = _build()
