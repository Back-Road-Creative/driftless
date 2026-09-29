"""Approving a schedule-scenario change request propagates: the draft baseline
``assist/schedule`` proposed becomes the plan every downstream reader walks
through ``assess.adapters.plan_baseline`` (that module's own docstring names
the Gantt page, the capacity heatmap, the PMBOK artifact map and the Scope &
Baseline document as exactly the surfaces bound to it) — so once a proposal is
approved, the Gantt bars, the earned-value figures and the capacity heatmap all
move together, off the SAME new baseline version, never three separate updates
that could drift out of step.

There is no ``#325`` propagation-manifest module on this branch to import, so
this is the local test the plan called for in its place: it drives the whole
loop through the real HTTP surface — propose, approve via the existing generic
PATCH boundary, then re-read three pages that each pick a baseline their own
way (a query in SQL, a query in SQL, an eager-loaded relationship) and assert
each one moved.
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
from driftless.db.changelog import register_changelog

AS_OF = date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"
# Straddles the heatmap's forward horizon (weeks counted from as_of), so crashing it
# moves which of those weeks carry the task's demand -- a window that had already
# closed by as_of would move on the Gantt page and nowhere the heatmap looks.
WINDOW = (AS_OF, AS_OF + timedelta(days=20))


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'propagation.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as session:
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
    person = m.Person(name="Ada")
    task = m.Task(
        name="Grade", workstream=stream, estimate=40.0, estimate_unit="hours", assignee=person
    )
    baseline = m.Baseline(project=proj, version=1, status="approved")
    db.add(
        m.BaselineLine(
            baseline=baseline,
            task=task,
            planned_cost=1000.0,
            planned_start=WINDOW[0],
            planned_finish=WINDOW[1],
        )
    )
    db.commit()
    return proj


def _pair(client: TestClient) -> dict[str, str]:
    return {"csrf_token": client.cookies["driftless_csrf"]}


def test_approving_a_proposed_schedule_change_moves_gantt_evm_and_the_heatmap(
    client: TestClient, db: Session, project: m.Project
) -> None:
    task_id = db.scalars(select(m.Task.id)).one()
    gantt_page = f"/projects/{project.id}/gantt{Q}"
    evm_page = f"/projects/{project.id}/assist/earned-value{Q}"
    heatmap_page = f"/org/heatmap{Q}"

    before_gantt = client.get(gantt_page).text
    before_evm = client.get(evm_page).text
    before_heatmap = client.get(heatmap_page).text

    schedule_page = client.get(f"/projects/{project.id}/assist/schedule{Q}&crash={task_id}:5")
    assert schedule_page.status_code == 200, schedule_page.text

    proposed = client.post(
        f"/projects/{project.id}/assist/schedule/propose",
        data={
            "as_of": AS_OF.isoformat(),
            "crash": f"{task_id}:5",
            "description": "Crash Grade by 5 days to hit the March deadline",
        }
        | _pair(client),
        follow_redirects=False,
    )
    assert proposed.status_code == 303, proposed.text

    change = db.scalars(select(m.ChangeRequest)).one()
    draft = db.scalars(select(m.Baseline).where(m.Baseline.status == "draft")).one()
    assert change.status == "proposed" and change.resulting_baseline_id is None

    # Still unapproved: nothing downstream has moved yet.
    assert client.get(gantt_page).text == before_gantt
    assert client.get(evm_page).text == before_evm

    # The existing human approval step: PATCH the draft, then the change request.
    approved_baseline = client.patch(
        f"/baselines/{draft.id}", json={"status": "approved", "approved_at": f"{AS_OF}T09:00:00"}
    )
    assert approved_baseline.status_code == 200, approved_baseline.text
    approved_change = client.patch(
        f"/change-requests/{change.id}",
        json={"status": "approved", "resulting_baseline_id": draft.id},
    )
    assert approved_change.status_code == 200, approved_change.text

    after_gantt = client.get(gantt_page).text
    after_evm = client.get(evm_page).text
    after_heatmap = client.get(heatmap_page).text
    assert after_gantt != before_gantt, "the Gantt page did not pick up the newly approved baseline"
    assert after_evm != before_evm, (
        "the earned-value page did not pick up the newly approved baseline"
    )
    assert after_heatmap != before_heatmap, "the capacity heatmap did not pick up the new window"
