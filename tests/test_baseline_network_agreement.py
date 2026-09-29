"""Surfacing test: a baseline whose own stored dates fall outside the window
``calc.network`` allows shows up as a schedule threat — read-only, never a
reconciliation. A task inside its own float is agreement, not disagreement.
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.assess.evaluators import schedule
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import (
    Baseline,
    BaselineLine,
    Business,
    Portfolio,
    Project,
    Task,
    TaskDependency,
    Workstream,
)

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


@pytest.fixture
def project(session: Session) -> Project:
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    session.add(project)
    session.commit()
    return project


def _line(baseline: Baseline, task: Task, start: date, finish: date) -> BaselineLine:
    return BaselineLine(
        baseline=baseline,
        task=task,
        planned_start=start,
        planned_finish=finish,
        planned_cost=1000.0,
    )


def _seed(session: Session, project: Project, b_start: date, b_finish: date) -> None:
    """A(1/1-1/4), B FS-dependent on A, B's stored window as given. C, also
    FS from A but much longer (1/4-1/20), gives B real float: B's own
    late_finish is bounded by C's project finish, not its own 4-day EF."""
    stream = Workstream(name="Post", project=project)
    a = Task(name="Shoot", workstream=stream, estimate_unit="hours", percent_complete=100)
    b = Task(name="Edit", workstream=stream, estimate_unit="hours", percent_complete=100)
    c = Task(name="Colour", workstream=stream, estimate_unit="hours", percent_complete=100)
    baseline = Baseline(project=project, version=1, status="approved")
    session.add_all(
        [
            _line(baseline, a, JAN, date(2026, 1, 4)),
            _line(baseline, b, b_start, b_finish),
            _line(baseline, c, date(2026, 1, 4), date(2026, 1, 20)),
        ]
    )
    session.commit()
    session.add_all(
        [
            TaskDependency(predecessor_task_id=a.id, successor_task_id=b.id, kind="FS"),
            TaskDependency(predecessor_task_id=a.id, successor_task_id=c.id, kind="FS"),
        ]
    )
    session.commit()


def test_schedule_red_when_a_stored_start_precedes_its_own_es(
    session: Session, project: Project
) -> None:
    # B stored starting before its own FS predecessor A even finishes (1/4).
    _seed(session, project, b_start=date(2026, 1, 2), b_finish=date(2026, 1, 8))
    assessment = schedule.evaluate(session, project, AS_OF)
    assert assessment.status == "red"
    assert "Edit" in assessment.threats[0].description
    assert "disagree" in assessment.threats[0].description


def test_schedule_green_when_a_task_is_scheduled_inside_its_own_float(
    session: Session, project: Project
) -> None:
    # B's own ES/EF is 1/4-1/8, but C's longer chain gives it float up to
    # 1/20 — stored dates late in that window are a legitimate placement
    # inside float, never a disagreement.
    _seed(session, project, b_start=date(2026, 1, 16), b_finish=date(2026, 1, 20))
    assert schedule.evaluate(session, project, AS_OF).status == "green"


def test_the_demo_seed_yields_no_disagreement_through_the_evaluator(tmp_path: Path) -> None:
    """Seeded through the validated API, same as production: no demo project's
    schedule threat, if any, may ever name a network disagreement."""
    from driftless.api.app import app as real_app
    from driftless.api.app import get_session
    from driftless.demo.cli import seed
    from driftless.demo.data import ANCHOR, demo_payload

    engine = new_engine(f"sqlite:///{tmp_path}/driftless.db")
    Base.metadata.create_all(engine)
    db = new_session_factory(engine)()
    real_app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(real_app) as c:

            def post(p: str, b: dict[str, Any]) -> int:
                r = c.post(p, json=b)
                assert r.status_code == 201, r.text
                return int(r.json()["id"])

            def patch(p: str, b: dict[str, Any]) -> None:
                r = c.patch(p, json=b)
                assert r.status_code == 200, r.text

            seed(post, demo_payload(ANCHOR), patch)
    finally:
        real_app.dependency_overrides.clear()

    for project in db.query(Project).all():
        for threat in schedule.evaluate(db, project, ANCHOR).threats:
            assert "disagree" not in threat.description, threat.description
