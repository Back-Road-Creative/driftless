"""The stakeholder assist page: ``/projects/{id}/assist/stakeholders`` — the
power/interest grid, the current-versus-desired engagement matrix with its
``?desired=<id>:<level>`` what-if, and the communications matrix. File-based
SQLite so every request connection sees the same seeded rows."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.models import Business, Portfolio, Project, Stakeholder

AS_OF = date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"


def _seed(session: Session) -> None:
    project = Project(
        name="Reels",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    session.add(project)
    session.flush()
    session.add(
        Stakeholder(
            project_id=project.id,
            name="Sponsor",
            interest="high",
            influence="high",
            comms_cadence="weekly",
        )
    )
    session.add(
        Stakeholder(
            project_id=project.id,
            name="Regulator",
            interest="low",
            influence="high",
            comms_cadence="monthly",
        )
    )
    session.commit()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as session:
        _seed(session)
    with factory() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app) as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def test_the_page_sorts_stakeholders_into_their_grid_quadrants(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/stakeholders{Q}").text
    assert body.count("Sponsor") >= 1
    assert body.count("Regulator") >= 1
    sponsor_cell = body[body.index("Manage closely") : body.index("Keep satisfied")]
    assert "Sponsor" in sponsor_cell
    satisfied_cell = body[body.index("Keep satisfied") : body.index("Keep informed")]
    assert "Regulator" in satisfied_cell


def test_the_engagement_matrix_defaults_desired_to_current(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/stakeholders{Q}").text
    assert "On Target" in body


def test_a_desired_what_if_opens_a_gap_and_names_an_action(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/stakeholders{Q}&desired=1:leading").text
    assert "behind" in body.lower()
    assert "Sponsor" in body


def test_an_out_of_project_stakeholder_id_is_refused(client: TestClient) -> None:
    page = client.get(f"/projects/1/assist/stakeholders{Q}&desired=999:leading")
    assert page.status_code == 422


def test_an_unknown_engagement_level_is_refused(client: TestClient) -> None:
    page = client.get(f"/projects/1/assist/stakeholders{Q}&desired=1:excited")
    assert page.status_code == 422


def test_the_communications_matrix_carries_each_stakeholders_own_cadence(
    client: TestClient,
) -> None:
    body = client.get(f"/projects/1/assist/stakeholders{Q}").text
    assert "Weekly" in body
    assert "Monthly" in body


def test_the_provenance_block_cites_the_techniques_this_page_runs(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/stakeholders{Q}").text
    assert "/techniques/stakeholder-analysis" in body
    assert "/techniques/stakeholder-engagement-assessment-matrix" in body
    assert "/techniques/communication-methods" in body


def test_an_unknown_project_is_404(client: TestClient) -> None:
    assert client.get(f"/projects/999/assist/stakeholders{Q}").status_code == 404


def test_a_pinned_as_of_regenerates_byte_identically(client: TestClient) -> None:
    url = f"/projects/1/assist/stakeholders{Q}"
    assert client.get(url).content == client.get(url).content
