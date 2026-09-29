"""``pmbok.schedule_facts.schedule_facts``: adapting stored rows into
``calc.network``'s pure inputs, gated the same way ``web.gantt`` gates its own read.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.calc.network import Dependency
from driftless.db import Base, new_engine, new_session_factory
from driftless.pmbok.schedule_facts import schedule_facts

JAN = date(2026, 1, 1)
AS_OF = date(2026, 3, 31)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'facts.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


def _project(db: Session) -> m.Project:
    portfolio = m.Portfolio(name="Content", business=m.Business(name="BRC"))
    project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    db.add(m.Workstream(name="Post", project=project))
    db.commit()
    return project


def test_no_approved_baseline_reads_as_no_facts(db: Session) -> None:
    project = _project(db)
    db.add(m.Baseline(project=project, version=1, status="draft"))
    db.commit()
    assert schedule_facts(db, project, AS_OF) is None


def test_an_approved_but_lineless_baseline_also_reads_as_no_facts(db: Session) -> None:
    project = _project(db)
    db.add(m.Baseline(project=project, version=1, status="approved"))
    db.commit()
    assert schedule_facts(db, project, AS_OF) is None


def test_duration_comes_from_the_planned_window_not_the_raw_estimate(db: Session) -> None:
    """A duration of 89 (JAN..AS_OF) must appear even though ``estimate`` is a
    delivery-mode-relative figure (hours here) carrying no calendar meaning."""
    project = _project(db)
    task = m.Task(
        name="Grade", workstream=project.workstreams[0], estimate=40.0, estimate_unit="hours"
    )
    baseline = m.Baseline(project=project, version=1, status="approved")
    db.add(
        m.BaselineLine(
            baseline=baseline,
            task=task,
            planned_cost=900.0,
            planned_start=JAN,
            planned_finish=AS_OF,
        )
    )
    db.commit()

    facts = schedule_facts(db, project, AS_OF)
    assert facts is not None
    aid = str(task.id)
    assert facts.network.activities[0].id == aid
    assert facts.network.activities[0].duration == (AS_OF - JAN).days
    assert facts.task_names[aid] == "Grade"
    assert facts.planned_cost[aid] == 900.0
    assert facts.cost_per_day[aid] == pytest.approx(900.0 / (AS_OF - JAN).days)
    assert facts.anchor == JAN


def test_dependencies_are_scoped_to_tasks_the_baseline_actually_lines(db: Session) -> None:
    """A ``TaskDependency`` naming a task with no line in this baseline cannot appear —
    the network calc would refuse a dangling reference outright."""
    project = _project(db)
    stream = project.workstreams[0]
    t1 = m.Task(name="Shoot", workstream=stream, estimate_unit="hours")
    t2 = m.Task(name="Edit", workstream=stream, estimate_unit="hours")
    outside = m.Task(name="Unlined", workstream=stream, estimate_unit="hours")
    baseline = m.Baseline(project=project, version=1, status="approved")
    db.add_all(
        [
            m.BaselineLine(
                baseline=baseline,
                task=t1,
                planned_cost=100.0,
                planned_start=JAN,
                planned_finish=JAN + timedelta(days=10),
            ),
            m.BaselineLine(
                baseline=baseline,
                task=t2,
                planned_cost=100.0,
                planned_start=JAN + timedelta(days=10),
                planned_finish=JAN + timedelta(days=20),
            ),
        ]
    )
    db.commit()
    db.add(m.TaskDependency(predecessor=t1, successor=t2, kind="FS", lag_days=1))
    db.add(m.TaskDependency(predecessor=outside, successor=t2, kind="FS"))
    db.commit()

    facts = schedule_facts(db, project, AS_OF)
    assert facts is not None
    assert facts.network.dependencies == (
        Dependency(predecessor=str(t1.id), successor=str(t2.id), kind="FS", lag=1),
    )


def test_demand_is_one_with_an_assignee_and_zero_without(db: Session) -> None:
    project = _project(db)
    stream = project.workstreams[0]
    person = m.Person(name="Ada")
    with_assignee = m.Task(name="Shoot", workstream=stream, estimate_unit="hours", assignee=person)
    without = m.Task(name="Edit", workstream=stream, estimate_unit="hours")
    baseline = m.Baseline(project=project, version=1, status="approved")
    db.add_all(
        [
            m.BaselineLine(
                baseline=baseline,
                task=with_assignee,
                planned_cost=1.0,
                planned_start=JAN,
                planned_finish=JAN + timedelta(days=1),
            ),
            m.BaselineLine(
                baseline=baseline,
                task=without,
                planned_cost=1.0,
                planned_start=JAN,
                planned_finish=JAN + timedelta(days=1),
            ),
        ]
    )
    db.commit()

    facts = schedule_facts(db, project, AS_OF)
    assert facts is not None
    assert facts.demand[str(with_assignee.id)] == 1.0
    assert facts.demand[str(without.id)] == 0.0


def test_three_point_safety_is_high_minus_value_and_zero_when_unrecorded(db: Session) -> None:
    project = _project(db)
    stream = project.workstreams[0]
    estimated = m.Task(name="Shoot", workstream=stream, estimate_unit="hours")
    plain = m.Task(name="Edit", workstream=stream, estimate_unit="hours")
    baseline = m.Baseline(project=project, version=1, status="approved")
    db.add_all(
        [
            m.BaselineLine(
                baseline=baseline,
                task=estimated,
                planned_cost=1.0,
                planned_start=JAN,
                planned_finish=JAN + timedelta(days=10),
            ),
            m.BaselineLine(
                baseline=baseline,
                task=plain,
                planned_cost=1.0,
                planned_start=JAN,
                planned_finish=JAN + timedelta(days=10),
            ),
        ]
    )
    db.commit()
    db.add(
        m.EstimateScenario(
            project_id=project.id,
            target="duration",
            subject_task_id=estimated.id,
            kind="three_point",
            value=10.0,
            low=8.0,
            high=14.0,
            actor="jp",
            as_of=JAN,
        )
    )
    db.commit()

    facts = schedule_facts(db, project, AS_OF)
    assert facts is not None
    assert facts.three_point_safety[str(estimated.id)] == pytest.approx(4.0)
    assert facts.three_point_safety.get(str(plain.id), 0.0) == 0.0
