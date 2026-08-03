"""Determinism and shape of the ``driftless demo seed`` payload -- pure builder, no live HTTP."""

from datetime import timedelta
from typing import Any

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
