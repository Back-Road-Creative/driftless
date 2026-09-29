"""Tier A resolvers: ``schedule_data`` and ``project_calendars`` now resolve against
the store, dropped from ``mapping.UNTRACKED_DISPOSITIONS`` into ``mapping.RESOLVERS``.

``schedule_data`` reads the same dated ``BaselineLine`` rows
:func:`mapping._schedule_baseline` already reads, plus the same ``TaskDependency``
edges :func:`mapping._project_schedule_network_diagram` already reads — present
only once BOTH exist: a dated activity list with no edges is a date list, and
edges with no dates are a diagram nobody has timed, neither one the working
schedule file PMBOK means by "schedule data".

``project_calendars`` reads whether a ``ProjectCalendar`` row
(``driftless/models/schedule.py``) exists for the project — the row itself IS
the calendar, so presence is exactly having one.

PMBOK 6.5 Develop Schedule (``driftless/pmbok/areas/schedule.py``) lists both
as REQUIRED outputs beside ``schedule_baseline`` and ``project_schedule``.
Adding resolvers with no producer of their own would flip 6.5 from "produce"
to "derived" in ``tests/test_e2e_knowledge_areas.py``'s categorisation, so
both are also marked ``optional_outputs`` there, mirroring ``risk_report``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.pmbok import mapping
from tests.conftest import AS_OF


def test_schedule_data_is_a_resolver_not_a_disposition() -> None:
    assert "schedule_data" in mapping.RESOLVERS
    assert "schedule_data" not in mapping.UNTRACKED_DISPOSITIONS


def test_project_calendars_is_a_resolver_not_a_disposition() -> None:
    assert "project_calendars" in mapping.RESOLVERS
    assert "project_calendars" not in mapping.UNTRACKED_DISPOSITIONS


def test_schedule_data_absent_with_dated_baseline_but_no_dependency_edges(
    project: m.Project, db: Session
) -> None:
    # The ``project`` fixture already seeds an approved, dated baseline line.
    status = mapping.resolve("schedule_data", project, db, AS_OF)
    assert not status.present
    assert not status.healthy


def test_schedule_data_present_once_dated_and_linked(project: m.Project, db: Session) -> None:
    predecessor = project.workstreams[0].tasks[0]
    successor = m.Task(name="Edit", workstream=project.workstreams[0], estimate_unit="hours")
    db.add(successor)
    db.commit()
    db.add(m.TaskDependency(predecessor_task_id=predecessor.id, successor_task_id=successor.id))
    db.commit()

    status = mapping.resolve("schedule_data", project, db, AS_OF)
    assert status.present
    assert status.healthy


def test_schedule_data_absent_with_dependency_but_no_approved_baseline(db: Session) -> None:
    portfolio = m.Portfolio(name="Other", business=m.Business(name="Other Co"))
    other_project = m.Project(name="Other", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="Other", project=other_project)
    predecessor = m.Task(name="A", workstream=stream, estimate_unit="hours")
    successor = m.Task(name="B", workstream=stream, estimate_unit="hours")
    db.add_all([predecessor, successor])
    db.commit()
    db.add(m.TaskDependency(predecessor_task_id=predecessor.id, successor_task_id=successor.id))
    db.commit()

    status = mapping.resolve("schedule_data", other_project, db, AS_OF)
    assert not status.present


def test_project_calendars_absent_with_no_calendar_row(project: m.Project, db: Session) -> None:
    status = mapping.resolve("project_calendars", project, db, AS_OF)
    assert not status.present
    assert not status.healthy


def test_project_calendars_present_once_a_calendar_is_filed(
    project: m.Project, db: Session
) -> None:
    db.add(m.ProjectCalendar(project=project, name="Standard"))
    db.commit()

    status = mapping.resolve("project_calendars", project, db, AS_OF)
    assert status.present
    assert status.healthy
    assert "1 calendar" in status.detail


def test_a_calendar_on_another_project_does_not_count(project: m.Project, db: Session) -> None:
    other_portfolio = m.Portfolio(name="Other", business=m.Business(name="Other Co"))
    other_project = m.Project(name="Other", portfolio=other_portfolio, delivery_mode="predictive")
    db.add(m.ProjectCalendar(project=other_project, name="Standard"))
    db.commit()

    status = mapping.resolve("project_calendars", project, db, AS_OF)
    assert not status.present
