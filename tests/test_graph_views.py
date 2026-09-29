"""``pmbok.graph_views`` derives the map's overview and neighbourhood views from
``GRAPH`` alone. Every expectation here is recomputed from ``GRAPH``/the
catalog, never restated as a literal — except the degree-zero node id, which
is named because naming it is the point of that test."""

from __future__ import annotations

import pytest

from driftless.pmbok import catalog
from driftless.pmbok.graph import GRAPH
from driftless.pmbok.graph_views import neighbourhood, overview

#: The nodes the catalog leaves with no tie at all — named, not derived, so a
#: change that silently connects or strands one of them fails here.
#: ``development_approach`` and ``performance_measurement_baseline`` left this
#: set once ``COMPONENT_OF`` gave them a ``part_of`` tie.
DEGREE_ZERO = ("technique:critical_chain_method",)


def test_overview_is_every_process_node_in_lifecycle_order() -> None:
    view = overview()
    assert [n.id for n in view.nodes] == [
        f"process:{p.id}"
        for p in sorted(
            catalog.PROCESSES,
            key=lambda p: (
                list(type(p.group)).index(p.group),
                tuple(int(part) for part in p.id.split(".")),
            ),
        )
    ]
    assert len(view.nodes) == len(GRAPH.by_kind("process"))
    assert {n.kind for n in view.nodes} == {"process"}


def test_overview_carries_only_the_ties_between_its_own_processes() -> None:
    view = overview()
    ids = {n.id for n in view.nodes}
    assert view.edges == tuple(e for e in GRAPH.edges if e.source in ids and e.target in ids)
    assert {e.kind for e in view.edges} == {"feeds"}


def test_overview_counts_report_the_view_against_the_whole_graph() -> None:
    view = overview()
    counts = view.counts()
    total_nodes, total_edges = GRAPH.size()
    assert (counts.nodes, counts.edges) == (len(view.nodes), len(view.edges))
    assert (counts.total_nodes, counts.total_edges) == (total_nodes, total_edges)


def test_neighbourhood_is_the_node_plus_exactly_its_graph_neighbours() -> None:
    node_id = "process:4.1"
    view = neighbourhood(node_id)
    assert view.focus == node_id
    assert {n.id for n in view.nodes} == {node_id, *GRAPH.neighbours(node_id)}
    assert [n.id for n in view.nodes] == [
        n.id
        for n in GRAPH.nodes
        if n.id
        in {
            node_id,
            *GRAPH.neighbours(node_id),
        }
    ]


def test_neighbourhood_keeps_only_edges_internal_to_its_own_nodes() -> None:
    view = neighbourhood("process:4.1")
    ids = {n.id for n in view.nodes}
    assert view.edges == tuple(e for e in GRAPH.edges if e.source in ids and e.target in ids)
    assert all(e.source in ids and e.target in ids for e in view.edges)
    counts = view.counts()
    assert (counts.nodes, counts.edges) == (len(ids), len(view.edges))


@pytest.mark.parametrize("node_id", DEGREE_ZERO)
def test_a_degree_zero_member_is_its_own_whole_neighbourhood(node_id: str) -> None:
    assert GRAPH.neighbours(node_id) == ()
    view = neighbourhood(node_id)
    assert [n.id for n in view.nodes] == [node_id]
    assert view.edges == ()
    assert (view.counts().nodes, view.counts().edges) == (1, 0)


def test_the_views_are_deterministic() -> None:
    assert overview() == overview()
    assert neighbourhood("technique:expert_judgment") == neighbourhood("technique:expert_judgment")


def test_an_unknown_node_id_is_refused_by_name() -> None:
    with pytest.raises(KeyError, match="process:0.0"):
        neighbourhood("process:0.0")
