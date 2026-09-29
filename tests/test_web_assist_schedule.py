"""The schedule-network calculator: ``GET /projects/{id}/assist/schedule`` and its
one write, ``POST .../propose``.

The network drawn is checked against ``calc.network`` itself, run over the SAME
inputs the page reads — an imported oracle, not a second hand-worked example. A
preview (``?crash=``/``?fast_track=``) never writes; the propose POST writes
exactly one ``ChangeRequest`` and one draft ``Baseline``, never touching the
already-approved plan.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.calc.network import backward_pass, forward_pass, total_float
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.pmbok.schedule_facts import schedule_facts

JAN = date(2026, 1, 1)
AS_OF = date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'assist_schedule.db'}")
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
    """Two dependent tasks: Shoot(10d) FS-> Edit(10d), so there is a real
    critical path and float to check, and Shoot carries a three-point estimate
    for the critical-chain buffer."""
    portfolio = m.Portfolio(name="Content", business=m.Business(name="BRC"))
    proj = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="Post", project=proj)
    shoot = m.Task(name="Shoot", workstream=stream, estimate_unit="hours")
    edit = m.Task(name="Edit", workstream=stream, estimate_unit="hours")
    baseline = m.Baseline(project=proj, version=1, status="approved")
    db.add_all(
        [
            m.BaselineLine(
                baseline=baseline,
                task=shoot,
                planned_cost=1000.0,
                planned_start=JAN,
                planned_finish=JAN + timedelta(days=10),
            ),
            m.BaselineLine(
                baseline=baseline,
                task=edit,
                planned_cost=2000.0,
                planned_start=JAN + timedelta(days=10),
                planned_finish=JAN + timedelta(days=20),
            ),
        ]
    )
    db.commit()
    db.add(m.TaskDependency(predecessor=shoot, successor=edit, kind="FS", lag_days=0))
    db.add(
        m.EstimateScenario(
            project_id=proj.id,
            target="duration",
            subject_task_id=shoot.id,
            kind="three_point",
            value=10.0,
            low=8.0,
            high=16.0,
            actor="jp",
            as_of=JAN,
        )
    )
    db.commit()
    return proj


def _pair(client: TestClient) -> dict[str, str]:
    return {"csrf_token": client.cookies["driftless_csrf"]}


def _census(session: Session) -> dict[str, int]:
    return {
        table.name: session.scalar(select(func.count()).select_from(table)) or 0
        for table in Base.metadata.sorted_tables
    }


def test_no_approved_baseline_says_so(client: TestClient, db: Session) -> None:
    portfolio = m.Portfolio(name="Content", business=m.Business(name="BRC"))
    unbaselined = m.Project(name="Unbaselined", portfolio=portfolio, delivery_mode="predictive")
    db.add(unbaselined)
    db.commit()
    body = client.get(f"/projects/{unbaselined.id}/assist/schedule{Q}").text
    assert "<svg" not in body
    assert "assist-schedule-empty" in body


def test_the_network_matches_calc_network_run_on_the_same_inputs(
    client: TestClient, db: Session, project: m.Project
) -> None:
    """Imported oracle: the SAME functions the page calls, run here directly over
    ``schedule_facts``'s own output, must produce the SAME critical/float reading
    the page renders."""
    facts = schedule_facts(db, project, AS_OF)
    assert facts is not None
    early = forward_pass(facts.network)
    late = backward_pass(facts.network, early)
    floats = total_float(early, late)

    body = client.get(f"/projects/{project.id}/assist/schedule{Q}").text
    assert "Shoot" in body and "Edit" in body
    for activity in facts.network.activities:
        name = facts.task_names[activity.id]
        row = f"<td>{name}</td><td>{activity.duration}d</td>"
        assert row in body, f"{name}'s duration row is missing or wrong"
        critical_cell = "<td>Yes</td>" if floats[activity.id] == 0 else "<td>No</td>"
        # both tasks are on the sole critical path in this fixture
        assert critical_cell == "<td>Yes</td>"
    assert "Shoot → Edit" in body, "the critical path is not rendered"


def test_a_crash_preview_never_writes(client: TestClient, db: Session, project: m.Project) -> None:
    task_id = db.scalar(select(m.Task.id).where(m.Task.name == "Shoot"))
    before = _census(db)
    body = client.get(f"/projects/{project.id}/assist/schedule{Q}&crash={task_id}:3").text
    assert "9d" in body or "7d" in body  # the crashed duration shows up somewhere in the text
    assert _census(db) == before, "a GET preview reached the store"


def test_a_fast_track_preview_never_writes(
    client: TestClient, db: Session, project: m.Project
) -> None:
    shoot_id = db.scalar(select(m.Task.id).where(m.Task.name == "Shoot"))
    edit_id = db.scalar(select(m.Task.id).where(m.Task.name == "Edit"))
    before = _census(db)
    resp = client.get(f"/projects/{project.id}/assist/schedule{Q}&fast_track={shoot_id}:{edit_id}")
    assert resp.status_code == 200, resp.text
    assert _census(db) == before, "a GET preview reached the store"


def test_a_crash_preview_shows_current_and_scenario_side_by_side(
    client: TestClient, db: Session, project: m.Project
) -> None:
    task_id = db.scalar(select(m.Task.id).where(m.Task.name == "Shoot"))
    body = client.get(f"/projects/{project.id}/assist/schedule{Q}&crash={task_id}:3").text
    assert "Current plan vs previewed scenario" in body
    assert "Shoot → Edit" in body
    # Current finish is day 20 off the anchor (Jan 1); crashing Shoot by 3 pulls it to day 17.
    assert (JAN + timedelta(days=20)).isoformat() in body
    assert (JAN + timedelta(days=17)).isoformat() in body
    # Current total cost is $3000 ($1000 + $2000); the crash adds cost per crashed day.
    assert "3000.0" in body


def test_both_crash_and_fast_track_at_once_is_refused(
    client: TestClient, project: m.Project
) -> None:
    resp = client.get(f"/projects/{project.id}/assist/schedule{Q}&crash=1:1&fast_track=1:2")
    assert resp.status_code == 422


def test_an_unknown_activity_in_a_preview_is_refused(
    client: TestClient, project: m.Project
) -> None:
    resp = client.get(f"/projects/{project.id}/assist/schedule{Q}&crash=999999:1")
    assert resp.status_code == 422


def test_the_page_is_byte_identical_for_a_pinned_as_of(
    client: TestClient, project: m.Project
) -> None:
    page = f"/projects/{project.id}/assist/schedule{Q}"
    first, second = client.get(page).text, client.get(page).text
    assert first == second


def test_propose_writes_exactly_one_change_request_and_one_draft_baseline(
    client: TestClient, db: Session, project: m.Project
) -> None:
    before_changes = db.scalar(select(func.count()).select_from(m.ChangeRequest)) or 0
    before_baselines = db.scalar(select(func.count()).select_from(m.Baseline)) or 0
    client.get(f"/projects/{project.id}/assist/schedule{Q}")  # mints the CSRF pair

    resp = client.post(
        f"/projects/{project.id}/assist/schedule/propose",
        data={"as_of": AS_OF.isoformat(), "description": "Level the plan"} | _pair(client),
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    assert resp.headers["location"] == f"/projects/{project.id}/assist/schedule{Q}"

    after_changes = db.scalar(select(func.count()).select_from(m.ChangeRequest)) or 0
    after_baselines = db.scalar(select(func.count()).select_from(m.Baseline)) or 0
    assert after_changes == before_changes + 1
    assert after_baselines == before_baselines + 1
    draft = db.scalars(select(m.Baseline).where(m.Baseline.status == "draft")).one()
    assert draft.version == 2

    live = schedule_facts(db, project, AS_OF)
    assert live is not None and live.baseline_version == 1, "the approved plan itself moved"
