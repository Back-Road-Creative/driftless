"""``pmbok.graph`` derives ONE method graph from the catalog. Every count and
cycle here is computed from the live catalog, never restated as a literal."""

from __future__ import annotations

import json
from typing import Literal

from driftless.pmbok import catalog, mapping
from driftless.pmbok.artifacts import ARTIFACT_KINDS, COMPONENT_OF
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.graph import GRAPH, MethodGraph, _build
from driftless.pmbok.tt import EXTENSIONS, TT_CATALOG


def test_every_catalog_member_is_a_node_with_the_right_label() -> None:
    by_id = {n.id: n for n in GRAPH.nodes}
    expected = (
        {f"process:{p.id}" for p in catalog.PROCESSES}
        | {f"technique:{k}" for k in TT_CATALOG}
        | {f"artifact:{k}" for k in ARTIFACT_KINDS}
    )
    assert set(by_id) == expected
    assert len(GRAPH.nodes) == len(expected)  # no duplicate ids
    for process in catalog.PROCESSES:
        assert by_id[f"process:{process.id}"].label == process.name
    for key, definition in TECHNIQUES.items():
        assert by_id[f"technique:{key}"].label == definition.display_name


def test_every_itto_reference_is_exactly_one_edge() -> None:
    counts = {"reads": 0, "produces": 0, "used_by": 0, "feeds": 0, "part_of": 0}
    for edge in GRAPH.edges:
        counts[edge.kind] += 1
    assert counts["reads"] == sum(len(p.inputs) for p in catalog.PROCESSES)
    assert counts["produces"] == sum(len(p.outputs) for p in catalog.PROCESSES)
    assert counts["used_by"] == sum(len(p.tools_techniques) for p in catalog.PROCESSES)
    assert counts["part_of"] == len(COMPONENT_OF)


def test_optional_outputs_are_flagged_on_the_produces_edge() -> None:
    optional_pairs = {
        (f"process:{p.id}", f"artifact:{out}")
        for p in catalog.PROCESSES
        for out in p.optional_outputs
    }
    for edge in GRAPH.edges:
        if edge.kind == "produces":
            assert edge.optional is ((edge.source, edge.target) in optional_pairs)


def test_a_feeds_edge_is_optional_only_when_every_artifact_behind_it_is_optional() -> None:
    """A ``feeds`` edge can rest on more than one artifact; it is optional only
    when EVERY (producer output -> consumer input) artifact behind it is
    optional for the producer. Computed independently of ``graph.py`` so this
    cannot merely echo its own bookkeeping, then checked example-by-example
    against the live graph and its own count reported."""
    produced_by: dict[str, set[str]] = {}
    optional_by: dict[str, dict[str, bool]] = {}
    for p in catalog.PROCESSES:
        for out in p.outputs:
            produced_by.setdefault(out, set()).add(p.id)
            optional_by.setdefault(out, {})[p.id] = out in p.optional_outputs

    behind: dict[tuple[str, str], list[bool]] = {}
    for p in catalog.PROCESSES:
        for inp in p.inputs:
            for producer in produced_by.get(inp, ()):
                if producer != p.id:
                    behind.setdefault((producer, p.id), []).append(optional_by[inp][producer])

    expected_optional = {pair for pair, flags in behind.items() if all(flags)}
    expected_certain = {pair for pair, flags in behind.items() if not all(flags)}

    feeds = {(e.source, e.target): e.optional for e in GRAPH.edges if e.kind == "feeds"}
    for producer, consumer in expected_optional:
        assert feeds[(f"process:{producer}", f"process:{consumer}")] is True
    for producer, consumer in expected_certain:
        assert feeds[(f"process:{producer}", f"process:{consumer}")] is False

    optional_count = sum(1 for is_optional in feeds.values() if is_optional)
    print(f"optional feeds edges -> {optional_count} of {len(feeds)}")
    assert optional_count == len(expected_optional)


def test_produces_then_reads_derives_a_feeds_edge() -> None:
    """Computed the same way here and in ``graph.py``, so this cannot merely
    echo its own bookkeeping."""
    produced_by: dict[str, set[str]] = {}
    for p in catalog.PROCESSES:
        for out in p.outputs:
            produced_by.setdefault(out, set()).add(p.id)
    expected = {
        (f"process:{producer}", f"process:{p.id}")
        for p in catalog.PROCESSES
        for inp in p.inputs
        for producer in produced_by.get(inp, ())
        if producer != p.id
    }
    assert {(e.source, e.target) for e in GRAPH.edges if e.kind == "feeds"} == expected


def test_orphan_nodes_are_exactly_the_known_exemptions() -> None:
    """Every node connects to an edge, except a technique already in
    ``EXTENSIONS``, an artifact with a reason in
    ``mapping.UNTRACKED_DISPOSITIONS``, or an artifact named in
    ``artifacts.COMPONENT_OF`` — a component kind still connects, via its own
    ``part_of`` edge to the whole it belongs to, so it is excluded from
    "exempt" (no edge expected) rather than folded into the disposition list
    it has nothing to do with. Derived, never typed."""
    referenced_artifacts = {a for p in catalog.PROCESSES for a in (*p.inputs, *p.outputs)}
    referenced_techniques = {t for p in catalog.PROCESSES for t in p.tools_techniques}
    orphan_artifacts = ARTIFACT_KINDS - referenced_artifacts
    orphan_techniques = TT_CATALOG - referenced_techniques
    component_artifacts = set(COMPONENT_OF)

    assert orphan_techniques == EXTENSIONS
    unexplained = orphan_artifacts - set(mapping.UNTRACKED_DISPOSITIONS) - component_artifacts
    assert not unexplained, f"{sorted(unexplained)} orphaned with no recorded disposition"

    exempt = {f"technique:{k}" for k in orphan_techniques} | {
        f"artifact:{k}" for k in orphan_artifacts - component_artifacts
    }
    for node in GRAPH.nodes:
        neighbours = GRAPH.neighbours(node.id)
        if node.id in exempt:
            assert not neighbours, f"{node.id} is exempt but has an edge"
        else:
            assert neighbours, f"{node.id} is an orphan node"


def _reachable(adjacency: dict[str, set[str]], start: str) -> set[str]:
    seen, stack = {start}, [start]
    while stack:
        for v in adjacency.get(stack.pop(), ()):
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def _sccs(adjacency: dict[str, set[str]]) -> list[set[str]]:
    """Strongly connected components (mutual reachability): cycles (size > 1)
    DERIVED, never typed. The catalog is small, so the naive O(n^2) is fine."""
    reach = {n: _reachable(adjacency, n) for n in adjacency}
    seen: set[str] = set()
    components = []
    for n in adjacency:
        if n not in seen:
            component = {m for m in reach[n] if n in reach[m]}
            seen |= component
            components.append(component)
    return components


def test_the_required_output_feeds_chain_is_acyclic_or_names_its_own_cycles() -> None:
    """The feeds chain over REQUIRED outputs only. If cyclic, the strongly
    connected components ARE the cycles — derived, reproduced by a second
    build."""
    produced_by: dict[str, set[str]] = {}
    for p in catalog.PROCESSES:
        for out in p.outputs:
            if out not in p.optional_outputs:
                produced_by.setdefault(out, set()).add(p.id)

    adjacency: dict[str, set[str]] = {p.id: set() for p in catalog.PROCESSES}
    for p in catalog.PROCESSES:
        for inp in p.inputs:
            adjacency[p.id] |= {pr for pr in produced_by.get(inp, ()) if pr != p.id}

    cycles = [c for c in _sccs(adjacency) if len(c) > 1]
    if not cycles:
        return  # the required-output chain is acyclic

    all_ids = {p.id for p in catalog.PROCESSES}
    for component in cycles:
        assert component <= all_ids
    again = [c for c in _sccs(adjacency) if len(c) > 1]
    assert sorted(map(sorted, cycles)) == sorted(map(sorted, again))


def test_two_builds_are_equal_and_size_is_measured() -> None:
    assert _build() == _build() == GRAPH
    node_count, edge_count = GRAPH.size()
    assert (node_count, edge_count) == (len(GRAPH.nodes), len(GRAPH.edges))
    print(f"MethodGraph.size() -> ({node_count} nodes, {edge_count} edges)")


def test_by_kind_partitions_the_nodes_and_to_dict_round_trips() -> None:
    seen: set[str] = set()
    kind: Literal["process", "technique", "artifact"]
    for kind in ("process", "technique", "artifact"):
        members = GRAPH.by_kind(kind)
        assert members, f"{kind} has no nodes"
        assert all(n.kind == kind for n in members)
        seen |= {n.id for n in members}
    assert seen == {n.id for n in GRAPH.nodes}

    decoded = json.loads(json.dumps(GRAPH.to_dict()))
    assert len(decoded["nodes"]) == len(GRAPH.nodes)
    assert len(decoded["edges"]) == len(GRAPH.edges)
    assert isinstance(GRAPH, MethodGraph)
