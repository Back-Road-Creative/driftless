"""Determinism and shape of the ``driftless demo seed`` payload -- pure builder, no live HTTP."""

from datetime import timedelta
from typing import Any

from driftless.calc.network import (
    Activity,
    Dependency,
    ScheduleNetwork,
    backward_pass,
    critical_path,
    forward_pass,
    total_float,
)
from driftless.demo.data import ANCHOR, demo_payload


def _projects(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for b in payload["businesses"] for pf in b["portfolios"] for p in pf["projects"]]


def _project_bac(project: dict[str, Any]) -> float:
    baseline = project["baseline"]
    return 0.0 if baseline is None else sum(line["planned_cost"] for line in baseline["lines"])


def _portfolio_bacs(payload: dict[str, Any]) -> dict[str, float]:
    return {
        pf["name"]: sum(_project_bac(p) for p in pf["projects"])
        for b in payload["businesses"]
        for pf in b["portfolios"]
    }


def test_demo_payload_is_deterministic() -> None:
    assert demo_payload(ANCHOR) == demo_payload(ANCHOR)


def test_shape_worst_risk_and_slipped_milestone() -> None:
    payload = demo_payload(ANCHOR)
    projects = _projects(payload)
    assert len(payload["businesses"]) == 2
    assert any(p["under_program"] for p in projects)
    assert any(not p["under_program"] for p in projects)
    assert sum(1 for p in projects if p["no_data"]) == 1

    exposures = sorted(
        (r["probability"] * r["impact"] for p in projects for r in p["risks"]), reverse=True
    )
    assert exposures[0] > exposures[1] * 10  # the worst risk, by a wide margin

    # Slipped: past due and still pending. Named as the property rather than
    # counted, so more milestones (one per status, for the board and the gantt)
    # cannot quietly cost the demo the slip its threat board is built on.
    milestones = [m for p in projects for m in p["milestones"]]
    assert [m for m in milestones if m["status"] == "pending" and m["target_date"] < ANCHOR]

    objectives = [o for b in payload["businesses"] for o in b["scorecard"]]
    assert {o["perspective"] for o in objectives} == {
        "financial",
        "customer_stakeholder",
        "internal_operations",
        "people_capability",
    }
    assert any(
        not metric["observations"] for objective in objectives for metric in objective["metrics"]
    )


def test_a_date_moves_when_the_anchor_moves() -> None:
    def milestone_date(anchor: Any) -> Any:
        projects = _projects(demo_payload(anchor))
        return next(m for p in projects for m in p["milestones"])["target_date"]

    later = ANCHOR + timedelta(days=7)
    assert milestone_date(later) - milestone_date(ANCHOR) == timedelta(days=7)


def test_baselines_cover_every_task_of_the_statused_projects_only() -> None:
    """Every non-no_data project gets an approved baseline whose lines name
    exactly its own tasks; the no-data project carries no baseline at all --
    the RAG-unknown state needs BAC == 0, which no baseline guarantees."""
    for project in _projects(demo_payload(ANCHOR)):
        task_names = {t["name"] for ws in project["workstreams"] for t in ws["tasks"]}
        if project["no_data"]:
            assert project["baseline"] is None
            assert project["budget_lines"] == [] and project["cost_entries"] == []
            continue
        baseline = project["baseline"]
        assert baseline is not None and baseline["status"] == "approved"
        assert {line["task"] for line in baseline["lines"]} == task_names


def test_both_portfolios_have_unequal_positive_bac() -> None:
    """BAC > 0 on both portfolios, and unequal, is what makes the treemap's
    area-proportional rectangles actually read as proportional in the demo."""
    bacs = _portfolio_bacs(demo_payload(ANCHOR))
    assert len(bacs) == 2
    values = list(bacs.values())
    assert all(v > 0 for v in values)
    assert values[0] != values[1]


def test_costs_spread_across_several_weeks_before_the_anchor() -> None:
    """AC needs shape for the S-curve/sparklines: several distinct dates, all
    before the as-of anchor, spanning multiple weeks -- not one lump sum."""
    for project in _projects(demo_payload(ANCHOR)):
        if project["no_data"]:
            continue
        dates = sorted({c["incurred_on"] for c in project["cost_entries"]})
        assert len(dates) >= 3
        assert all(d < ANCHOR for d in dates)
        assert (dates[-1] - dates[0]).days >= 21


def test_exactly_one_project_runs_adaptively_and_carries_a_full_iteration_record() -> None:
    """One adaptive project is what keeps the flow surfaces off their empty state;
    the others stay predictive, so the predictive demo is not traded away for it."""
    projects = _projects(demo_payload(ANCHOR))
    (adaptive,) = [p for p in projects if p.get("delivery_mode")]
    assert adaptive["delivery_mode"] == "hybrid"
    assert len([p for p in projects if not p.get("delivery_mode")]) == 3

    sprints = adaptive["sprints"]
    assert len([s for s in sprints if s["end_offset"] < 0]) >= 3, "a velocity band needs three"
    assert [s for s in sprints if s["start_offset"] <= 0 <= s["end_offset"]], "one in flight"
    statuses = {i["status"] for i in adaptive["backlog_items"]}
    assert statuses == {"proposed", "ready", "in_progress", "done"}
    assert [i for i in adaptive["impediments"] if i["resolved_offset"] is None]


def _rollout(payload: dict[str, Any]) -> dict[str, Any]:
    """The predictive project the gantt page is demonstrated on, by name."""
    return next(p for p in _projects(payload) if p["name"] == "Season 4 Rollout")


def _rollout_network(payload: dict[str, Any]) -> ScheduleNetwork:
    """The predictive project's plan as ``calc.network`` reads it: one activity per
    baseline line, its duration the planned window, one edge per seeded dependency --
    the same two inputs ``pmbok.schedule_facts`` builds the live network from."""
    project = _rollout(payload)
    lines = project["baseline"]["lines"]
    return ScheduleNetwork(
        activities=tuple(
            Activity(
                id=line["task"], duration=(line["planned_finish"] - line["planned_start"]).days
            )
            for line in lines
        ),
        dependencies=tuple(
            Dependency(d["predecessor"], d["successor"], d["kind"], d["lag_days"])
            for d in project["dependencies"]
        ),
    )


def test_the_predictive_plan_is_a_chained_network_not_a_flat_list() -> None:
    """Every edge names a task the baseline covers, and at least one task is both
    somebody's predecessor and somebody else's successor -- a chain, not a star."""
    network = _rollout_network(demo_payload(ANCHOR))
    ids = {activity.id for activity in network.activities}
    predecessors = {dep.predecessor for dep in network.dependencies}
    successors = {dep.successor for dep in network.dependencies}
    assert predecessors <= ids and successors <= ids
    assert predecessors & successors, "no task both follows one task and leads another"


def test_the_predictive_plan_computes_a_multi_task_critical_path_and_real_float() -> None:
    """The two figures the schedule assistant exists to show. Asserted as
    properties of the computed network, never as a row count: a longer flat list
    of tasks would still leave the critical path one task long and nothing slack."""
    network = _rollout_network(demo_payload(ANCHOR))
    early = forward_pass(network)
    late = backward_pass(network, early)
    longest = max(critical_path(network, early, late), key=len)
    assert len(longest) > 2, f"critical path is not a chain: {longest}"
    floats = total_float(early, late)
    assert [aid for aid, days in floats.items() if days > 0], "no task carries any float"
    assert [aid for aid, days in floats.items() if days == 0], "nothing is critical"


def test_the_predictive_plan_spans_the_project_rather_than_one_corner() -> None:
    """The gantt draws one bar per baseline line over a single scale, so a plan
    whose windows all sit in one place draws a corner. Distinct starts spread on
    both sides of the as-of are what make it read as a schedule."""
    lines = _rollout(demo_payload(ANCHOR))["baseline"]["lines"]
    starts = sorted({line["planned_start"] for line in lines})
    assert len(starts) >= 5, "too few distinct start dates to read as a timeline"
    assert starts[0] < ANCHOR < max(line["planned_finish"] for line in lines)
    milestones = _rollout(demo_payload(ANCHOR))["milestones"]
    assert len(milestones) >= 4, "a schedule marks more than a couple of commitments"
