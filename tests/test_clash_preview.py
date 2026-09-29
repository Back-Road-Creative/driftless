"""``web.heatmap.clash_preview``: the resource-clash preview the assignment form on
``/projects/{id}/assist/team`` reads before a write, never after one — the same
``allocation``/``capacity_cell`` figures the org heatmap grid draws, so a preview
can never disagree with the grid it previews. No auto-levelling: it only reports.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.db import Base, new_engine, new_session_factory
from driftless.web.heatmap import clash_preview

AS_OF = date(2026, 2, 16)  # a Monday, so the horizon's first column is its own week
MONDAY = AS_OF


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'clash.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


def _project(db: Session) -> m.Project:
    portfolio = m.Portfolio(name="Content", business=m.Business(name="BRC"))
    return m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")


def test_none_when_the_task_carries_no_estimate(db: Session) -> None:
    project = _project(db)
    stream = m.Workstream(name="Post", project=project)
    ada = m.Person(name="Ada", capacity_hours=40.0)
    bare = m.Task(name="Bare", workstream=stream, estimate_unit="hours")
    db.add_all([project, ada, bare])
    db.commit()
    assert clash_preview(db, AS_OF, ada.id, bare.id) is None


def test_none_when_the_task_has_no_planned_window_yet(db: Session) -> None:
    project = _project(db)
    stream = m.Workstream(name="Post", project=project)
    ada = m.Person(name="Ada", capacity_hours=40.0)
    task = m.Task(name="Edit", workstream=stream, estimate_unit="hours", estimate=10.0)
    db.add_all([project, ada, task])
    db.commit()
    assert clash_preview(db, AS_OF, ada.id, task.id) is None


def test_the_preview_shows_hours_added_without_writing_anything(db: Session) -> None:
    project = _project(db)
    stream = m.Workstream(name="Post", project=project)
    ada = m.Person(name="Ada", capacity_hours=40.0)
    task = m.Task(name="Edit", workstream=stream, estimate_unit="hours", estimate=32.0)
    baseline = m.Baseline(project=project, version=1, status="approved")
    db.add_all([project, ada, task, baseline])
    db.commit()
    db.add(
        m.BaselineLine(
            baseline=baseline,
            task=task,
            planned_cost=0.0,
            planned_start=MONDAY,
            planned_finish=MONDAY + timedelta(days=4),
        )
    )
    db.commit()

    before = db.query(m.Task).filter(m.Task.id == task.id).one().assignee_id

    preview = clash_preview(db, AS_OF, ada.id, task.id)

    assert preview is not None
    assert preview["person"] == "Ada"
    assert preview["task"] == "Edit"
    assert preview["current"]["cells"][0]["hours"] == "0"
    assert preview["proposed"]["cells"][0]["hours"] == "32"
    assert preview["would_overallocate"] is False  # 32/40 = 80%, at but not over the red line
    assert db.query(m.Task).filter(m.Task.id == task.id).one().assignee_id == before


def test_would_overallocate_when_the_addition_pushes_past_the_red_threshold(
    db: Session,
) -> None:
    project = _project(db)
    stream = m.Workstream(name="Post", project=project)
    ada = m.Person(name="Ada", capacity_hours=40.0)
    task = m.Task(name="Edit", workstream=stream, estimate_unit="hours", estimate=45.0)
    baseline = m.Baseline(project=project, version=1, status="approved")
    db.add_all([project, ada, task, baseline])
    db.commit()
    db.add(
        m.BaselineLine(
            baseline=baseline,
            task=task,
            planned_cost=0.0,
            planned_start=MONDAY,
            planned_finish=MONDAY + timedelta(days=4),
        )
    )
    db.commit()

    preview = clash_preview(db, AS_OF, ada.id, task.id)

    assert preview is not None
    assert preview["would_overallocate"] is True


def test_unknown_person_or_task_previews_nothing(db: Session) -> None:
    assert clash_preview(db, AS_OF, 999_999, 999_999) is None
