"""``services.schedule_scenarios``: crash/fast-track network transforms, and the
one write — ``propose_baseline_change`` — which files a draft baseline and a
change request, never touching the live plan.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.calc.network import Activity, Dependency, ScheduleNetwork
from driftless.pmbok.schedule_facts import schedule_facts
from driftless.services.schedule_scenarios import (
    CrashInput,
    UnknownActivityError,
    UnknownProcessError,
    crashed_network,
    fast_tracked_network,
    propose_baseline_change,
    scenario_dates,
)

AS_OF = date(2026, 3, 31)
JAN = date(2026, 1, 1)


def _network() -> ScheduleNetwork:
    return ScheduleNetwork(
        activities=(Activity("A", 10), Activity("B", 10)),
        dependencies=(Dependency("A", "B", "FS", 0),),
    )


def test_crashed_network_shortens_only_the_named_activity() -> None:
    crashed = crashed_network(_network(), "A", 3)
    durations = {a.id: a.duration for a in crashed.activities}
    assert durations == {"A": 7, "B": 10}
    assert crashed.dependencies == _network().dependencies


def test_crashed_network_floors_at_zero_rather_than_going_negative() -> None:
    crashed = crashed_network(_network(), "A", 99)
    assert next(a.duration for a in crashed.activities if a.id == "A") == 0


def test_crashed_network_refuses_an_unknown_activity() -> None:
    with pytest.raises(UnknownActivityError):
        crashed_network(_network(), "Z", 1)


def test_fast_tracked_network_turns_the_named_fs_pair_into_ss() -> None:
    tracked = fast_tracked_network(_network(), "A", "B")
    assert tracked.dependencies == (Dependency("A", "B", "SS", 0),)
    assert tracked.activities == _network().activities


def test_fast_tracked_network_refuses_a_pair_that_is_not_fs() -> None:
    ss_network = ScheduleNetwork(
        activities=(Activity("A", 10), Activity("B", 10)),
        dependencies=(Dependency("A", "B", "SS", 0),),
    )
    with pytest.raises(UnknownActivityError):
        fast_tracked_network(ss_network, "A", "B")


def test_neither_transform_mutates_the_network_handed_in() -> None:
    base = _network()
    crashed_network(base, "A", 3)
    fast_tracked_network(base, "A", "B")
    assert base == _network()


def test_propose_baseline_change_writes_exactly_one_change_and_one_draft_baseline(
    db: Session, project: m.Project
) -> None:
    facts = schedule_facts(db, project, AS_OF)
    assert facts is not None
    before_changes = db.scalars(select(m.ChangeRequest)).all()
    before_baselines = db.scalars(select(m.Baseline)).all()

    change, draft = propose_baseline_change(db, project, AS_OF, "Slip two days", "6.6", facts, None)

    after_changes = db.scalars(select(m.ChangeRequest)).all()
    after_baselines = db.scalars(select(m.Baseline)).all()
    assert len(after_changes) == len(before_changes) + 1
    assert len(after_baselines) == len(before_baselines) + 1
    assert (change.status, change.origin_process_id, change.resulting_baseline_id) == (
        "proposed",
        "6.6",
        None,
    )
    assert draft.status == "draft"
    assert draft.version == max(b.version for b in before_baselines) + 1


def test_propose_baseline_change_leaves_the_approved_plan_untouched(
    db: Session, project: m.Project
) -> None:
    """The write is a draft beside the live plan, never a rewrite of it."""
    facts = schedule_facts(db, project, AS_OF)
    assert facts is not None
    live = facts.network.activities[0]
    propose_baseline_change(
        db, project, AS_OF, "Crash it", "6.6", facts, CrashInput(int(live.id), 2)
    )
    still_live = schedule_facts(db, project, AS_OF)
    assert still_live is not None
    assert still_live.network == facts.network, "the approved network moved"


def test_propose_baseline_change_refuses_an_unknown_process(
    db: Session, project: m.Project
) -> None:
    facts = schedule_facts(db, project, AS_OF)
    assert facts is not None
    with pytest.raises(UnknownProcessError):
        propose_baseline_change(db, project, AS_OF, "x", "99.9", facts, None)


def test_scenario_dates_crash_shortens_the_crashed_activitys_window(
    db: Session, project: m.Project
) -> None:
    facts = schedule_facts(db, project, AS_OF)
    assert facts is not None
    task_id = int(facts.network.activities[0].id)
    _, _, base_finishes = scenario_dates(facts, None)
    _, _, crashed_finishes = scenario_dates(facts, CrashInput(task_id, 3))
    aid = str(task_id)
    assert crashed_finishes[aid] == base_finishes[aid] - 3


def test_propose_baseline_change_crash_adds_its_cost_per_day_times_days_removed(
    db: Session, project: m.Project
) -> None:
    facts = schedule_facts(db, project, AS_OF)
    assert facts is not None
    task_id = int(facts.network.activities[0].id)
    aid = str(task_id)
    original_cost = facts.planned_cost[aid]
    cost_per_day = facts.cost_per_day[aid]

    _, draft = propose_baseline_change(
        db, project, AS_OF, "Crash it 2 days", "6.6", facts, CrashInput(task_id, 2)
    )
    line = db.scalar(
        select(m.BaselineLine).where(
            m.BaselineLine.baseline_id == draft.id, m.BaselineLine.task_id == task_id
        )
    )
    assert line is not None
    assert line.planned_cost == pytest.approx(round(original_cost + cost_per_day * 2, 2))
    assert line.planned_finish == line.planned_start + timedelta(
        days=facts.network.activities[0].duration - 2
    )
