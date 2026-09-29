"""``GET /projects/{id}/assist/team?preview_person_id=&preview_task_id=``: the
resource-clash preview on the assignment form — read-only, before the write.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory

AS_OF = date(2026, 2, 16)
Q = f"?as_of={AS_OF.isoformat()}"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'assist_team_clash.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as browser:
        yield browser
    real_app.dependency_overrides.clear()


@pytest.fixture
def project(db: Session) -> m.Project:
    portfolio = m.Portfolio(name="Content", business=m.Business(name="BRC"))
    proj = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="Post", project=proj)
    ada = m.Person(name="Ada", capacity_hours=40.0)
    task = m.Task(name="Edit", workstream=stream, estimate_unit="hours", estimate=32.0)
    baseline = m.Baseline(project=proj, version=1, status="approved")
    db.add_all([proj, ada, task, baseline])
    db.commit()
    db.add(
        m.BaselineLine(
            baseline=baseline,
            task=task,
            planned_cost=0.0,
            planned_start=AS_OF,
            planned_finish=AS_OF + timedelta(days=4),
        )
    )
    db.commit()
    return proj


def test_no_preview_params_shows_no_clash_table(client: TestClient, project: m.Project) -> None:
    body = client.get(f"/projects/{project.id}/assist/team{Q}").text
    assert "Clash preview:" not in body


def test_a_clash_preview_never_writes(client: TestClient, db: Session, project: m.Project) -> None:
    ada_id = db.scalar(select(m.Person.id).where(m.Person.name == "Ada"))
    task_id = db.scalar(select(m.Task.id).where(m.Task.name == "Edit"))
    before = db.scalar(select(m.Task.assignee_id).where(m.Task.id == task_id))

    body = client.get(
        f"/projects/{project.id}/assist/team{Q}&preview_person_id={ada_id}&preview_task_id={task_id}"
    ).text

    assert "Clash preview: Ada with Edit" in body
    assert "32" in body
    after = db.scalar(select(m.Task.assignee_id).where(m.Task.id == task_id))
    assert after == before


def test_the_page_is_byte_identical_for_a_pinned_as_of(
    client: TestClient, db: Session, project: m.Project
) -> None:
    ada_id = db.scalar(select(m.Person.id).where(m.Person.name == "Ada"))
    task_id = db.scalar(select(m.Task.id).where(m.Task.name == "Edit"))
    page = f"/projects/{project.id}/assist/team{Q}&preview_person_id={ada_id}&preview_task_id={task_id}"
    first, second = client.get(page).text, client.get(page).text
    assert first == second
