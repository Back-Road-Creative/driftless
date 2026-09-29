"""``services.schedule_scenarios.scenario_project_summary``: the current-plan-vs-
scenario comparison ``web.assist_schedule`` shows beside its network preview —
finish, critical path and total cost, computed the same way
``propose_baseline_change`` would write them, never touching the store.
"""

from __future__ import annotations

from datetime import date, timedelta

from driftless.calc.network import Activity, Dependency, ScheduleNetwork
from driftless.pmbok.schedule_facts import ScheduleFacts
from driftless.services.schedule_scenarios import CrashInput, scenario_project_summary

ANCHOR = date(2026, 1, 1)


def _facts() -> ScheduleFacts:
    return ScheduleFacts(
        baseline_version=1,
        anchor=ANCHOR,
        network=ScheduleNetwork(
            activities=(Activity("1", 10), Activity("2", 10)),
            dependencies=(Dependency("1", "2", "FS", 0),),
        ),
        task_names={"1": "Shoot", "2": "Edit"},
        planned_cost={"1": 1000.0, "2": 2000.0},
        cost_per_day={"1": 100.0, "2": 200.0},
        demand={"1": 1.0, "2": 1.0},
        three_point_safety={},
    )


def test_current_plan_summary_matches_the_stored_baseline() -> None:
    summary = scenario_project_summary(_facts(), None)
    assert summary.finish == ANCHOR + timedelta(days=20)
    assert summary.critical_paths == (("1", "2"),)
    assert summary.total_cost == 3000.0


def test_crash_scenario_pulls_the_finish_in_and_adds_the_crash_cost() -> None:
    summary = scenario_project_summary(_facts(), CrashInput(task_id=1, days=3))
    assert summary.finish == ANCHOR + timedelta(days=17)
    assert summary.critical_paths == (("1", "2"),)
    # Task 1's own line: $1000 planned + 3 crashed days at $100/day = $1300.
    # Task 2 unchanged at $2000. Total: $3300.
    assert summary.total_cost == 3300.0


def test_scenario_never_mutates_the_facts_handed_in() -> None:
    facts = _facts()
    before = facts.network
    scenario_project_summary(facts, CrashInput(task_id=1, days=3))
    assert facts.network == before
