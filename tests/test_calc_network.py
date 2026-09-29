"""Tests for the schedule-network core: forward/backward pass, float, and
critical path over hand-computed textbook networks.

Primary fixture (all finish-to-start, no lag): A(3) feeds B(4) and C(2);
B and C both feed D(5); D feeds E(3). The arithmetic for every figure below
is written out so it can be checked without running anything.

    ES/EF: A 0/3.  B 3/7 (pred A: EF 3 + 0).  C 3/5 (pred A: EF 3 + 0).
           D 7/12 (max(EF_B=7, EF_C=5) = 7).  E 12/15 (pred D: EF 12 + 0).
    Project finish = 15.
    LS/LF: E 12/15 (no successor -> LF = finish).
           D 7/12 (succ E: LS_E - 0 = 12).
           C 5/7 (succ D: LS_D - 0 = 7).
           B 3/7 (succ D: LS_D - 0 = 7).
           A 0/3 (succ B: LS_B - 0 = 3; succ C: LS_C - 0 = 5; min = 3).
    Total float: A 0, B 0, C 2, D 0, E 0 -> critical path A-B-D-E.
    Free float: A 0 (min(ES_B - EF_A, ES_C - EF_A) = min(0, 0)).
                B 0 (ES_D - EF_B = 7 - 7).
                C 2 (ES_D - EF_C = 7 - 5).
                D 0 (ES_E - EF_D = 12 - 12).
                E 0 (no successor -> equals its own total float).
"""

from __future__ import annotations

import pytest

from driftless.calc.network import (
    Activity,
    Dependency,
    ScheduleNetwork,
    backward_pass,
    critical_path,
    forward_pass,
    free_float,
    network_diagram,
    network_disagreements,
    resource_levelling_preview,
    schedule_compression_preview,
    total_float,
)

PRIMARY = ScheduleNetwork(
    activities=(
        Activity("A", 3),
        Activity("B", 4),
        Activity("C", 2),
        Activity("D", 5),
        Activity("E", 3),
    ),
    dependencies=(
        Dependency("A", "B", "FS"),
        Dependency("A", "C", "FS"),
        Dependency("B", "D", "FS"),
        Dependency("C", "D", "FS"),
        Dependency("D", "E", "FS"),
    ),
)


def test_forward_pass_matches_the_hand_computed_early_dates() -> None:
    early = forward_pass(PRIMARY)
    assert (early["A"].early_start, early["A"].early_finish) == (0, 3)
    assert (early["B"].early_start, early["B"].early_finish) == (3, 7)
    assert (early["C"].early_start, early["C"].early_finish) == (3, 5)
    assert (early["D"].early_start, early["D"].early_finish) == (7, 12)
    assert (early["E"].early_start, early["E"].early_finish) == (12, 15)


def test_backward_pass_matches_the_hand_computed_late_dates() -> None:
    early = forward_pass(PRIMARY)
    late = backward_pass(PRIMARY, early)
    assert (late["E"].late_start, late["E"].late_finish) == (12, 15)
    assert (late["D"].late_start, late["D"].late_finish) == (7, 12)
    assert (late["C"].late_start, late["C"].late_finish) == (5, 7)
    assert (late["B"].late_start, late["B"].late_finish) == (3, 7)
    assert (late["A"].late_start, late["A"].late_finish) == (0, 3)


def test_total_and_free_float_match_the_hand_computed_figures() -> None:
    early = forward_pass(PRIMARY)
    late = backward_pass(PRIMARY, early)
    assert total_float(early, late) == {"A": 0, "B": 0, "C": 2, "D": 0, "E": 0}
    assert free_float(PRIMARY, early, late) == {"A": 0, "B": 0, "C": 2, "D": 0, "E": 0}


def test_single_critical_path() -> None:
    early = forward_pass(PRIMARY)
    late = backward_pass(PRIMARY, early)
    assert critical_path(PRIMARY, early, late) == (("A", "B", "D", "E"),)


def test_multiple_critical_paths_when_two_branches_tie() -> None:
    # Same network with C stretched to 4 days: C's EF becomes 7, tying B's,
    # so both A-B-D-E and A-C-D-E finish the project with zero float.
    tied = ScheduleNetwork(
        activities=(
            Activity("A", 3),
            Activity("B", 4),
            Activity("C", 4),
            Activity("D", 5),
            Activity("E", 3),
        ),
        dependencies=PRIMARY.dependencies,
    )
    early = forward_pass(tied)
    late = backward_pass(tied, early)
    assert critical_path(tied, early, late) == (
        ("A", "B", "D", "E"),
        ("A", "C", "D", "E"),
    )


def test_network_diagram_flags_only_critical_nodes_and_edges() -> None:
    early = forward_pass(PRIMARY)
    late = backward_pass(PRIMARY, early)
    diagram = network_diagram(PRIMARY, early, late)
    critical_nodes = {node.id for node in diagram.nodes if node.critical}
    assert critical_nodes == {"A", "B", "D", "E"}
    critical_edges = {(edge.source, edge.target) for edge in diagram.edges if edge.critical}
    assert critical_edges == {("A", "B"), ("B", "D"), ("D", "E")}


@pytest.mark.parametrize(
    ("kind", "lag", "expected_es", "expected_ef"),
    [
        ("FS", 1, 3, 5),  # ES = pred EF + lag = 2 + 1; EF = ES + B's own 2-day duration
        ("SS", 1, 1, 3),  # ES = pred ES + lag = 0 + 1
        ("FF", 1, 3, 5),  # ES = pred EF + lag - B's duration = 4 + 1 - 2
        ("SF", 6, 4, 6),  # ES = pred ES + lag - B's duration = 0 + 6 - 2
    ],
)
def test_each_dependency_kind_constrains_the_successor(
    kind: str, lag: int, expected_es: int, expected_ef: int
) -> None:
    duration_a = 4 if kind == "FF" else 2
    network = ScheduleNetwork(
        activities=(Activity("A", duration_a), Activity("B", 2)),
        dependencies=(Dependency("A", "B", kind, lag=lag),),  # type: ignore[arg-type]
    )
    early = forward_pass(network)
    assert (early["B"].early_start, early["B"].early_finish) == (expected_es, expected_ef)


def test_a_negative_lag_is_a_lead_that_starts_the_successor_early() -> None:
    network = ScheduleNetwork(
        activities=(Activity("A", 5), Activity("B", 3)),
        dependencies=(Dependency("A", "B", "FS", lag=-2),),
    )
    early = forward_pass(network)
    # Without the lead B would start at 5; the two-day lead pulls it to 3.
    assert (early["B"].early_start, early["B"].early_finish) == (3, 6)


def test_cycle_refuses_naming_the_activities_caught_in_it() -> None:
    cyclic = ScheduleNetwork(
        activities=(Activity("A", 1), Activity("B", 1)),
        dependencies=(Dependency("A", "B", "FS"), Dependency("B", "A", "FS")),
    )
    with pytest.raises(ValueError, match=r"cycle among activities \['A', 'B'\]"):
        forward_pass(cyclic)


def test_dangling_dependency_reference_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="unknown activity 'Z'"):
        ScheduleNetwork(
            activities=(Activity("A", 1),),
            dependencies=(Dependency("A", "Z", "FS"),),
        )


def test_activity_refuses_a_negative_duration() -> None:
    with pytest.raises(ValueError, match="duration is negative"):
        Activity("A", -1)


def test_schedule_network_refuses_a_duplicate_activity_id() -> None:
    with pytest.raises(ValueError, match="duplicate activity id"):
        ScheduleNetwork(activities=(Activity("A", 1), Activity("A", 2)), dependencies=())


@pytest.mark.parametrize(
    ("kind", "lag", "duration_a", "expected_ls", "expected_lf"),
    [
        ("FS", 1, 2, 0, 2),  # B's LS is its own EF - lag = 3 - 1 = 2; A's LF = 2
        ("SS", 1, 2, 0, 2),  # A's LF = B.late_start - lag + duration_A = 1 - 1 + 2
        ("FF", 1, 4, 0, 4),  # A's LF = B.late_finish - lag = 5 - 1
        ("SF", 6, 2, 0, 2),  # A's LF = B.late_finish - lag + duration_A = 6 - 6 + 2
    ],
)
def test_each_dependency_kind_constrains_the_predecessors_late_dates(
    kind: str, lag: int, duration_a: int, expected_ls: int, expected_lf: int
) -> None:
    """The backward-pass twin of ``test_each_dependency_kind_constrains_the_successor``:
    B is terminal (no outgoing edges, so its own late dates equal the project finish),
    and A's late dates are pulled backward through each of the four kinds in turn."""
    network = ScheduleNetwork(
        activities=(Activity("A", duration_a), Activity("B", 2)),
        dependencies=(Dependency("A", "B", kind, lag=lag),),  # type: ignore[arg-type]
    )
    early = forward_pass(network)
    late = backward_pass(network, early)
    assert (late["A"].late_start, late["A"].late_finish) == (expected_ls, expected_lf)


@pytest.mark.parametrize(
    ("kind", "lag", "duration_a", "expected_free_float"),
    [
        ("SS", 1, 2, 0),  # succ.ES - (A.ES + lag) = 1 - (0 + 1)
        ("FF", 1, 4, 0),  # succ.EF - (A.EF + lag) = 5 - (4 + 1)
        ("SF", 6, 2, 0),  # succ.EF - (A.ES + lag) = 6 - (0 + 6)
    ],
)
def test_each_dependency_kind_constrains_free_float(
    kind: str, lag: int, duration_a: int, expected_free_float: int
) -> None:
    """The free-float twin: A's only outgoing edge is this one kind, so its slack is
    read straight off that edge's own formula rather than the FS case PRIMARY covers."""
    network = ScheduleNetwork(
        activities=(Activity("A", duration_a), Activity("B", 2)),
        dependencies=(Dependency("A", "B", kind, lag=lag),),  # type: ignore[arg-type]
    )
    early = forward_pass(network)
    late = backward_pass(network, early)
    assert free_float(network, early, late)["A"] == expected_free_float


def test_forward_and_backward_pass_are_deterministic() -> None:
    assert forward_pass(PRIMARY) == forward_pass(PRIMARY)
    early = forward_pass(PRIMARY)
    assert backward_pass(PRIMARY, early) == backward_pass(PRIMARY, early)


def test_schedule_compression_preview_never_mutates_the_network() -> None:
    early = forward_pass(PRIMARY)
    late = backward_pass(PRIMARY, early)
    before = PRIMARY
    scenario = schedule_compression_preview(
        PRIMARY, early, late, cost_per_day={"A": 500.0, "B": 200.0, "C": 50.0, "D": 300.0}
    )
    assert PRIMARY == before  # nothing about the input changed
    # C has float and is excluded even though it is cheapest; cost order otherwise holds.
    assert [c.activity_id for c in scenario.crash_candidates] == ["B", "D", "A"]


def test_fast_track_candidates_are_critical_path_finish_to_start_pairs() -> None:
    early = forward_pass(PRIMARY)
    late = backward_pass(PRIMARY, early)
    scenario = schedule_compression_preview(PRIMARY, early, late, cost_per_day={})
    pairs = {(c.predecessor, c.successor) for c in scenario.fast_track_candidates}
    assert pairs == {("A", "B"), ("B", "D"), ("D", "E")}


def test_resource_levelling_preview_shifts_only_non_critical_activities() -> None:
    early = forward_pass(PRIMARY)
    late = backward_pass(PRIMARY, early)
    scenario = resource_levelling_preview(
        PRIMARY, early, late, demand={"A": 1, "B": 1, "C": 1, "D": 1, "E": 1}
    )
    # C is the only activity with float (2); everything else stays at its ES.
    assert scenario.proposed_starts["C"] == late["C"].late_start
    for activity_id in ("A", "B", "D", "E"):
        assert scenario.proposed_starts[activity_id] == early[activity_id].early_start


def test_network_disagreements_finds_a_stored_start_before_es() -> None:
    # A(3) feeds B(4) via FS: B's window is [3, 7], zero float. Stored B
    # starts on day 1, before A even finishes — a real contradiction.
    network = ScheduleNetwork(
        activities=(Activity("A", 3), Activity("B", 4)),
        dependencies=(Dependency("A", "B", "FS"),),
    )
    disagreements = network_disagreements(
        network,
        stored_start={"A": 0, "B": 1},
        stored_finish={"A": 3, "B": 7},
    )
    assert len(disagreements) == 1
    d = disagreements[0]
    assert d.activity_id == "B"
    assert (d.stored_start, d.early_start) == (1, 3)
    assert (d.stored_finish, d.late_finish) == (7, 7)


def test_network_disagreements_treats_a_task_scheduled_inside_its_own_float_as_agreement() -> None:
    # C has float 2: ES/EF 3/5, LS/LF 5/7. Stored at its LATEST start (5) is
    # a legitimate placement inside float, not a disagreement.
    early = forward_pass(PRIMARY)
    late = backward_pass(PRIMARY, early)
    stored_start = {aid: early[aid].early_start for aid in early}
    stored_finish = {aid: early[aid].early_finish for aid in early}
    stored_start["C"] = late["C"].late_start
    stored_finish["C"] = late["C"].late_finish
    assert network_disagreements(PRIMARY, stored_start, stored_finish) == ()


def test_network_disagreements_flags_a_span_and_respects_tolerance() -> None:
    network = ScheduleNetwork(
        activities=(Activity("A", 3), Activity("B", 4)),
        dependencies=(Dependency("A", "B", "FS"),),
    )
    # A stored span that is not B's own 4-day duration, even inside [ES, LF].
    disagreements = network_disagreements(
        network, stored_start={"A": 0, "B": 4}, stored_finish={"A": 3, "B": 7}
    )
    assert [d.activity_id for d in disagreements] == ["B"]
    # One day early, within a tolerance of 1 -> no disagreement reported.
    assert (
        network_disagreements(
            network,
            stored_start={"A": 0, "B": 2},
            stored_finish={"A": 3, "B": 6},
            tolerance=1,
        )
        == ()
    )
    # An activity absent from the stored maps is skipped, never guessed at.
    assert network_disagreements(network, stored_start={"A": 0}, stored_finish={"A": 3}) == ()


def test_network_disagreements_skips_an_isolated_activity() -> None:
    # C has no dependency edge at all, so nothing constrains its stored dates
    # to the OTHER activities' project finish — a stored window far past what
    # a "leaf bound by project finish" reading would compute is not a
    # disagreement, since the network makes no claim about C at all.
    network = ScheduleNetwork(
        activities=(Activity("A", 3), Activity("B", 4), Activity("C", 2)),
        dependencies=(Dependency("A", "B", "FS"),),
    )
    assert (
        network_disagreements(
            network,
            stored_start={"A": 0, "B": 3, "C": 100},
            stored_finish={"A": 3, "B": 7, "C": 102},
        )
        == ()
    )
