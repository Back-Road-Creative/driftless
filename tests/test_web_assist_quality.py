"""The quality workbench page: ``GET /projects/{id}/assist/quality``.

Control charts, a Pareto of measurement failures, a statistical-sampling what-if, a
root-cause worksheet over one issue, a cost-of-quality what-if and an audit checklist
read off the quality management plan narrative — every figure read straight off the
project's own rows, or typed into a no-write what-if. Nothing here writes.
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
    Issue,
    NarrativeArtifact,
    Portfolio,
    Project,
    QualityMeasurement,
    QualityMetric,
)

AS_OF = date(2026, 3, 31)
JAN = date(2026, 1, 1)
Q = f"?as_of={AS_OF.isoformat()}"


def _seed(session: Session) -> None:
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    session.add(project)
    metric = QualityMetric(
        project=project, name="Defect rate", direction="lower_is_better", upper_bound=2.0
    )
    session.add(metric)
    session.add_all(
        QualityMeasurement(
            project=project,
            quality_metric=metric,
            metric="Defect rate",
            target_value=2.0,
            actual_value=actual,
            unit="%",
            measured_on=on,
        )
        for on, actual in ((JAN, 1.0), (AS_OF, 5.0))
    )
    session.add(Issue(project=project, description="Late render", raised_on=AS_OF, status="open"))
    session.add(
        NarrativeArtifact(
            project=project,
            kind="quality_management_plan",
            body="Inspect every reel before delivery. Log a defect the moment it is found.",
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
    body = client.get(f"/projects/1/assist/quality{Q}").text
    assert "GMS" in body


def test_control_chart_draws_from_two_or_more_readings(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/quality{Q}").text
    assert "Defect rate" in body
    assert "control-chart" in body
    assert "<polyline" in body


def test_pareto_ranks_the_out_of_tolerance_reading(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/quality{Q}").text
    assert "Vital few" in body
    assert "Defect rate" in body


def test_sampling_plan_is_blank_until_all_three_inputs_are_given(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/quality{Q}").text
    assert "sampling-formula" not in body


def test_sampling_plan_computes_when_population_confidence_and_margin_are_given(
    client: TestClient,
) -> None:
    body = client.get(
        f"/projects/1/assist/quality{Q}&population=500&confidence=0.95&margin=0.05"
    ).text
    assert "sampling-formula" in body


def test_sampling_plan_ignores_an_invalid_confidence_rather_than_500ing(client: TestClient) -> None:
    resp = client.get(f"/projects/1/assist/quality{Q}&population=500&confidence=0.5&margin=0.05")
    assert resp.status_code == 200
    assert "sampling-formula" not in resp.text


def test_root_cause_worksheet_lists_the_projects_issues(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/quality{Q}").text
    assert "Late render" in body


def test_root_cause_worksheet_traces_the_selected_issue(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/quality{Q}&issue=1").text
    assert "Fishbone: Late render" in body
    assert "Method" in body and "Machine" in body


def test_five_whys_names_the_last_answer_as_the_root_cause(client: TestClient) -> None:
    body = client.get(
        f"/projects/1/assist/quality{Q}&issue=1&why=No+buffer&why=Under-resourced"
    ).text
    assert "five-whys-root-cause" in body
    assert "Under-resourced" in body


def test_cost_of_quality_is_blank_until_all_four_bands_are_given(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/quality{Q}").text
    assert "coq-interpretation" not in body


def test_cost_of_quality_computes_when_all_four_bands_are_given(client: TestClient) -> None:
    body = client.get(
        f"/projects/1/assist/quality{Q}"
        "&prevention=100&appraisal=50&internal_failure=20&external_failure=10"
    ).text
    assert "coq-interpretation" in body
    assert "front-loaded" in body


def test_audit_checklist_reads_the_quality_management_plan_narrative(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/quality{Q}").text
    assert "Inspect every reel before delivery." in body
    assert "Log a defect the moment it is found." in body


def test_audit_checklist_says_nothing_filed_yet_with_no_narrative(
    client: TestClient, db: Session
) -> None:
    db.query(NarrativeArtifact).delete()
    db.commit()
    body = client.get(f"/projects/1/assist/quality{Q}").text
    assert "No quality management plan filed yet" in body


def test_the_page_writes_nothing(client: TestClient, db: Session) -> None:
    before = db.query(QualityMeasurement).count()
    client.get(
        f"/projects/1/assist/quality{Q}&population=100&confidence=0.9&margin=0.1"
        "&prevention=1&appraisal=1&internal_failure=1&external_failure=1&issue=1&why=x"
    )
    assert db.query(QualityMeasurement).count() == before


def test_the_page_carries_provenance_for_its_three_routed_techniques(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/quality{Q}").text
    for name in ("Root Cause Analysis", "Cost of Quality", "Audits"):
        assert name in body
    assert "8.1" in body
    assert "8.2" in body


def test_every_routed_technique_links_its_own_reference_page(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/quality{Q}").text
    assert "/techniques/root-cause-analysis" in body
    assert "/techniques/cost-of-quality" in body
    assert "/techniques/audits" in body


def test_an_unknown_project_404s(client: TestClient) -> None:
    assert client.get(f"/projects/999/assist/quality{Q}").status_code == 404


def test_action_launch_href_routes_the_three_registered_techniques() -> None:
    for key in ("root_cause_analysis", "cost_of_quality", "audits"):
        action = Action("probe", "label", key, "why", "project:7")
        assert action.launch_href == "/projects/7/assist/quality"
        assert model.ASSISTANT_ROUTES[key] == "/projects/{project_id}/assist/quality"
