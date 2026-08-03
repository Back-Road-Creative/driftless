"""Contract tests for the per-project delivery records.

The orphan-FK cases lean on the ``PRAGMA foreign_keys=ON`` listener in
``driftless.db.base`` exactly as ``test_hierarchy.py`` does — without it SQLite
accepts every one of them and these tests would pass while proving nothing.
"""

from collections.abc import Callable, Iterator
from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from driftless.db import Base, new_engine, new_session_factory
from driftless.models import (
    Baseline,
    BaselineLine,
    Business,
    Milestone,
    Portfolio,
    Project,
    Sprint,
    Task,
    Workstream,
)

START, FINISH = date(2026, 1, 1), date(2026, 1, 10)


@pytest.fixture
def session() -> Iterator[Session]:
    """An in-memory SQLite session with the full schema created."""
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


@pytest.fixture
def project(session: Session) -> Project:
    """A committed project carrying one task, ready to hang records off."""
    portfolio = Portfolio(name="Content Brands", business=Business(name="Back Road Creative"))
    project = Project(name="GoMoveShift 2026", delivery_mode="agile", portfolio=portfolio)
    workstream = Workstream(name="Editing", project=project)
    session.add(Task(name="Cut the trailer", workstream=workstream))
    session.commit()
    return project


@pytest.fixture
def task(session: Session, project: Project) -> Task:
    stored = session.get(Task, 1)
    assert stored is not None
    return stored


def _line(baseline: Baseline, task: Task | None = None, **overrides: object) -> BaselineLine:
    fields: dict[str, object] = {
        "planned_start": START,
        "planned_finish": FINISH,
        "planned_cost": 100.0,
        **overrides,
    }
    return BaselineLine(baseline=baseline, task=task, **fields)


def _sprint(**overrides: object) -> Sprint:
    fields: dict[str, object] = {"start_date": START, "end_date": FINISH, **overrides}
    return Sprint(name="Sprint 1", **fields)


def test_baseline_is_time_phased_per_task(session: Session, project: Project, task: Task) -> None:
    approved = datetime(2026, 1, 1, 9, 0)
    baseline = Baseline(project=project, version=1, status="approved", approved_at=approved)
    session.add(_line(baseline, task))
    session.commit()

    stored = session.get(Baseline, 1)
    assert stored is not None
    assert stored.approved_at == approved
    assert [
        (ln.task_id, ln.planned_start, ln.planned_finish, ln.planned_cost) for ln in stored.lines
    ] == [(task.id, START, FINISH, 100.0)]


def test_rebaselining_adds_a_version_with_its_own_lines(
    session: Session, project: Project, task: Task
) -> None:
    first = Baseline(project=project, version=1, status="superseded")
    second = Baseline(project=project, version=2, status="approved")
    session.add_all([_line(first, task), _line(second, task, planned_cost=250.0)])
    session.commit()

    stored = session.scalars(select(Baseline).where(Baseline.project_id == project.id)).all()
    assert sorted(baseline.version for baseline in stored) == [1, 2]
    assert first.lines[0].planned_cost == 100.0
    assert second.lines[0].planned_cost == 250.0


def test_milestone_and_sprint_persist(session: Session, project: Project) -> None:
    session.add(
        Milestone(
            project=project,
            name="Season one live",
            target_date=FINISH,
            baseline_date=START,
            status="at_risk",
        )
    )
    session.add(_sprint(project=project, committed_points=21, completed_points=13))
    session.commit()

    milestone, sprint = session.get(Milestone, 1), session.get(Sprint, 1)
    assert milestone is not None and milestone.baseline_date == START
    assert sprint is not None and sprint.completed_points == 13
    assert not hasattr(sprint, "velocity"), "velocity is derived on read, never stored"


def test_duplicate_baseline_version_per_project_is_rejected(
    session: Session, project: Project
) -> None:
    session.add_all([Baseline(project=project, version=1), Baseline(project=project, version=1)])
    with pytest.raises(IntegrityError):
        session.commit()


INVALID_ROWS: dict[str, Callable[[Project, Task], object]] = {
    "orphan baseline": lambda p, t: Baseline(project_id=999, version=1),
    "baseline version zero": lambda p, t: Baseline(project=p, version=0),
    "baseline version negative": lambda p, t: Baseline(project=p, version=-1),
    "baseline status off-vocabulary": lambda p, t: Baseline(project=p, version=1, status="ok'd"),
    "orphan baseline line": lambda p, t: _line(Baseline(project=p, version=1), task_id=999),
    "finish precedes start": lambda p, t: _line(
        Baseline(project=p, version=1), t, planned_finish=date(2025, 12, 1)
    ),
    "negative planned cost": lambda p, t: _line(
        Baseline(project=p, version=1), t, planned_cost=-1.0
    ),
    "orphan milestone": lambda p, t: Milestone(project_id=999, name="M", target_date=FINISH),
    "milestone status off-vocabulary": lambda p, t: Milestone(
        project=p, name="M", target_date=FINISH, status="soon"
    ),
    "orphan sprint": lambda p, t: _sprint(project_id=999),
    "sprint end precedes start": lambda p, t: _sprint(project=p, start_date=FINISH, end_date=START),
    "negative committed points": lambda p, t: _sprint(project=p, committed_points=-1),
    "negative completed points": lambda p, t: _sprint(project=p, completed_points=-1),
}


@pytest.mark.parametrize("build", INVALID_ROWS.values(), ids=list(INVALID_ROWS))
def test_database_rejects_invalid_row(
    session: Session, project: Project, task: Task, build: Callable[[Project, Task], object]
) -> None:
    session.add(build(project, task))
    with pytest.raises(IntegrityError):
        session.commit()
