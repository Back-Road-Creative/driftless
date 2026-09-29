"""The scope worksheet page: ``GET /projects/{id}/assist/scope``.

One page, one section per Scope-family technique with no calculable output:
product analysis, context diagram, prototypes, benchmarking and inspection.
Every figure is read straight off the project's existing rows — narrative
prose, stakeholders, milestones — never computed and never written.
"""

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
from driftless.db.changelog import register_changelog
from driftless.models import (
    Business,
    Milestone,
    NarrativeArtifact,
    Portfolio,
    Project,
    Stakeholder,
)

AS_OF = date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"


def _seed(session: Session) -> None:
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    session.add(project)
    session.add(Stakeholder(project=project, name="Ada Lovelace", interest="high"))
    session.add(Stakeholder(project=project, name="Grace Hopper", interest="medium"))
    session.add(Milestone(project=project, name="Kickoff", target_date=AS_OF, status="met"))
    session.add(Milestone(project=project, name="Launch", target_date=AS_OF, status="pending"))
    session.add(
        NarrativeArtifact(
            project=project, kind="project_scope_statement", body="Ship the new fleet tracker."
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
    with TestClient(real_app, base_url="https://testserver") as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def test_the_page_renders_the_project(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/scope{Q}").text
    assert "GMS" in body


def test_product_analysis_shows_the_plain_questions_and_the_filed_answer(
    client: TestClient,
) -> None:
    body = client.get(f"/projects/1/assist/scope{Q}").text
    assert "Product breakdown" in body
    assert "Systems analysis" in body
    assert "Value engineering" in body
    assert "Ship the new fleet tracker." in body


def test_product_analysis_says_nothing_filed_yet_when_the_project_has_no_scope_statement(
    client: TestClient, db: Session
) -> None:
    db.query(NarrativeArtifact).delete()
    db.commit()
    body = client.get(f"/projects/1/assist/scope{Q}").text
    assert "nothing filed yet" in body.lower()


def test_context_diagram_lists_stakeholders_as_actors(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/scope{Q}").text
    assert "Ada Lovelace" in body
    assert "Grace Hopper" in body


def test_prototype_checklist_is_tied_to_whether_requirements_are_filed(
    client: TestClient,
) -> None:
    body = client.get(f"/projects/1/assist/scope{Q}").text
    assert "disposable" in body.lower()
    assert "No requirements documentation is filed yet" in body


def test_benchmarking_table_adds_a_column_per_against_param(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/scope{Q}&against=Acme&against=Globex").text
    assert "Acme" in body
    assert "Globex" in body


def test_inspection_lists_milestones_with_status_and_a_checklist_result(
    client: TestClient,
) -> None:
    body = client.get(f"/projects/1/assist/scope{Q}").text
    assert "Kickoff" in body
    assert "Launch" in body
    assert "1 of 2" in body


def test_the_page_writes_nothing(client: TestClient, db: Session) -> None:
    before = db.query(NarrativeArtifact).count()
    client.get(f"/projects/1/assist/scope{Q}&against=Acme")
    assert db.query(NarrativeArtifact).count() == before


def test_the_page_carries_its_provenance_for_every_technique(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/scope{Q}").text
    for name in ("Product Analysis", "Context Diagram", "Prototypes", "Benchmarking", "Inspection"):
        assert name in body
    assert "5.2" in body
    assert "5.3" in body
    assert "5.5" in body


def test_every_technique_links_its_own_reference_page(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/scope{Q}").text
    assert "/techniques/product-analysis" in body
    assert "/techniques/context-diagram" in body
    assert "/techniques/prototypes" in body
    assert "/techniques/benchmarking" in body
    assert "/techniques/inspection" in body


def test_an_unknown_project_404s(client: TestClient) -> None:
    assert client.get(f"/projects/999/assist/scope{Q}").status_code == 404


def test_action_launch_href_formats_in_the_one_place_the_model_owns() -> None:
    action = Action("probe", "label", "context_diagram", "why", "project:42")
    assert action.launch_href == "/projects/42/assist/scope"
    assert model.ASSISTANT_ROUTES["context_diagram"] == "/projects/{project_id}/assist/scope"
