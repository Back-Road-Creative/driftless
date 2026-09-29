"""Small, targeted tests for branches no existing test file's scope fits.

Each case below closes exactly one missed line the coverage floor flagged —
grouped here rather than invented a new module per line, since none of them
share a home with an existing suite.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business, Portfolio, Project, Task, TaskDependency, Workstream
from driftless.services.schedule_writes import _adjacency
from driftless.services.scope_writes import file_deliverable

JAN = date(2026, 1, 1)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


@pytest.fixture
def project(session: Session) -> Project:
    project = Project(
        name="GMS", portfolio=Portfolio(name="Content", business=Business(name="BRC"))
    )
    session.add(project)
    session.commit()
    return project


def _task(session: Session, project: Project, name: str) -> Task:
    stream = Workstream(name="Post", project=project)
    task = Task(name=name, workstream=stream, estimate_unit="hours")
    session.add(task)
    session.commit()
    return task


def test_adjacency_excludes_the_dependencys_own_current_edge(
    session: Session, project: Project
) -> None:
    """``exclude_id`` drops one dependency's own edge from the walk, so checking a
    patch against itself never reads as a cycle."""
    a, b = _task(session, project, "A"), _task(session, project, "B")
    dependency = TaskDependency(predecessor_task_id=a.id, successor_task_id=b.id)
    session.add(dependency)
    session.commit()

    excluded = _adjacency(session, exclude_id=dependency.id)
    assert excluded == {}
    kept = _adjacency(session)
    assert kept == {a.id: [b.id]}


def test_file_deliverable_validates_and_inserts_a_wbs_node(
    session: Session, project: Project
) -> None:
    payload = s.DeliverableIn(project_id=project.id, name="Phase 1 report", wbs_code="1.1")
    deliverable = file_deliverable(session, payload)
    assert deliverable.id is not None
    assert deliverable.wbs_code == "1.1"


def test_a_patch_before_validator_passes_through_a_non_dict_input_unchanged() -> None:
    """``_dropping_frozen_fk``'s strip only applies to a raw dict body — a caller who
    hands ``model_validate`` something that is not one (a JSON scalar, say) is passed
    through unchanged, and pydantic's own type check is what refuses it, not the strip."""
    with pytest.raises(ValidationError):
        s.TaskPatch.model_validate(42)
