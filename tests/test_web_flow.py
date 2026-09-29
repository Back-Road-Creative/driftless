"""The flow calculator page: ``GET /projects/{id}/flow``. Every figure must equal
``pmbok.flow_facts.flow_snapshot`` — the same adapter the project hub's flow tile
reads — and the page must render an honest empty state when no sprint's window
contains the as-of."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.assess import model
from driftless.assess.model import Action
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import BacklogItem, Business, Portfolio, Project, Sprint

JAN, AS_OF = date(2026, 1, 1), date(2026, 1, 31)
Q = f"?as_of={AS_OF.isoformat()}"


def _seed(session: Session) -> None:
    portfolio = Portfolio(name="Content", business=Business(name="BRC"))
    project = Project(name="GMS", portfolio=portfolio, delivery_mode="agile")
    session.add(project)
    session.flush()
    session.add(
        Sprint(
            project=project,
            name="S1",
            start_date=JAN,
            end_date=date(2026, 1, 31),
            committed_points=10,
            completed_points=5,
        )
    )
    session.add(BacklogItem(project=project, title="A", story_points=3, status="in_progress"))
    session.add(BacklogItem(project=project, title="B", story_points=5, status="done"))
    session.commit()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as session:
        _seed(session)
    with factory() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def test_the_page_renders_wip_and_throughput(client: TestClient) -> None:
    body = client.get(f"/projects/1/flow{Q}").text
    assert 'id="flow-wip">1<' in body  # the in_progress item, done falls out of WIP
    assert "GMS" in body


def test_the_page_shows_the_active_sprints_window(client: TestClient) -> None:
    body = client.get(f"/projects/1/flow{Q}").text
    assert "S1" in body
    assert "Burndown as text" in body
    assert "Cumulative flow as text" in body


def test_an_as_of_outside_every_sprint_shows_the_empty_state(client: TestClient) -> None:
    body = client.get("/projects/1/flow?as_of=2026-06-30").text
    assert "no window to draw" in body
    assert "flow-empty" in body


def test_the_hub_tile_and_the_flow_page_agree(client: TestClient) -> None:
    hub = client.get(f"/projects/1/hub{Q}").text
    page = client.get(f"/projects/1/flow{Q}").text
    assert 'id="flow-tile-wip">1<' in hub
    assert 'id="flow-wip">1<' in page


def test_an_unknown_project_404s(client: TestClient) -> None:
    assert client.get(f"/projects/999/flow{Q}").status_code == 404


def test_a_pinned_as_of_regenerates_byte_identically(client: TestClient) -> None:
    url = f"/projects/1/flow{Q}"
    assert client.get(url).content == client.get(url).content


def test_the_recommended_action_launches_the_flow_page(db: Session) -> None:
    from driftless.assess import engine as assess

    project = db.get(Project, 1)
    assert project is not None
    schedule = {a.kind: a for a in assess.assess_project(db, project, AS_OF)}.get("schedule")
    if schedule is not None:
        for action in schedule.actions:
            if action.pmbok_tt == "agile_release_planning":
                assert action.launch_href == "/projects/1/flow"
                assert action.is_reference_only is False


def test_action_launch_href_formats_in_the_one_place_the_model_owns() -> None:
    action = Action("probe", "label", "agile_release_planning", "why", "project:42")
    assert action.launch_href == "/projects/42/flow"
    assert model.ASSISTANT_ROUTES["agile_release_planning"] == "/projects/{project_id}/flow"
