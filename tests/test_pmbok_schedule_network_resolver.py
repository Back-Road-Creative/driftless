"""Tier A resolver: ``project_schedule_network_diagram`` now resolves against the
store, dropped from ``mapping.UNTRACKED_DISPOSITIONS`` into ``mapping.RESOLVERS``. It
reads ``TaskDependency`` rows (``driftless/models/schedule.py``) scoped to this
project's own tasks — the typed precedence edges PMBOK 6.3 Sequence Activities
produces — never a second, stored copy of the network.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.pmbok import mapping
from tests.conftest import AS_OF


def test_network_diagram_is_a_resolver_not_a_disposition() -> None:
    assert "project_schedule_network_diagram" in mapping.RESOLVERS
    assert "project_schedule_network_diagram" not in mapping.UNTRACKED_DISPOSITIONS


def test_absent_with_tasks_but_no_dependency_edges(project: m.Project, db: Session) -> None:
    status = mapping.resolve("project_schedule_network_diagram", project, db, AS_OF)
    assert not status.present
    assert not status.healthy


def test_present_once_a_dependency_links_two_of_the_projects_tasks(
    project: m.Project, db: Session
) -> None:
    stream = project.workstreams[0]
    successor = m.Task(name="Edit", workstream=stream, estimate_unit="hours")
    db.add(successor)
    db.commit()
    predecessor = project.workstreams[0].tasks[0]
    db.add(m.TaskDependency(predecessor_task_id=predecessor.id, successor_task_id=successor.id))
    db.commit()

    status = mapping.resolve("project_schedule_network_diagram", project, db, AS_OF)
    assert status.present
    assert status.healthy
    assert "1 dependency edge" in status.detail


def test_an_edge_between_another_projects_tasks_does_not_count(
    project: m.Project, db: Session
) -> None:
    other_portfolio = m.Portfolio(name="Other", business=m.Business(name="Other Co"))
    other_project = m.Project(name="Other", portfolio=other_portfolio, delivery_mode="predictive")
    other_stream = m.Workstream(name="Other", project=other_project)
    t1 = m.Task(name="A", workstream=other_stream, estimate_unit="hours")
    t2 = m.Task(name="B", workstream=other_stream, estimate_unit="hours")
    db.add_all([t1, t2])
    db.commit()
    db.add(m.TaskDependency(predecessor_task_id=t1.id, successor_task_id=t2.id))
    db.commit()

    status = mapping.resolve("project_schedule_network_diagram", project, db, AS_OF)
    assert not status.present
