"""Contract for the organization-configuration page.

The dashboard answers how delivery is going.  This page answers a different
first-run question: which operational structure exists, and what validated
API resource establishes each missing part.
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.pmbok import catalog, tailoring
from driftless.pmbok.model import ProcessGroup
from driftless.web import create_configuration_router
from driftless.web.configuration import _tailoring_rows


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(create_configuration_router())
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app) as test_client:
        yield test_client


def test_configuration_page_counts_operating_structure_and_names_write_paths(
    client: TestClient, db: Session
) -> None:
    business = m.Business(name="Northstar")
    portfolio = m.Portfolio(name="Change", business=business)
    program = m.Program(name="Modernization", portfolio=portfolio)
    department = m.Department(name="Delivery", business=business)
    project = m.Project(
        name="Fleet", portfolio=portfolio, program=program, responsible_department=department
    )
    person = m.Person(name="Ari", department=department)
    metric = m.QualityMetric(
        project=project,
        name="Escaped defects",
        direction="lower_is_better",
        upper_bound=2,
    )
    objective = m.StrategicObjective(
        business=business, perspective="internal_operations", name="Ship reliably"
    )
    scorecard_metric = m.ScorecardMetricDefinition(
        objective=objective,
        name="Escaped defects",
        direction="lower_is_better",
        unit="count",
        target_value=1,
        amber_threshold=2,
        red_threshold=4,
        cadence_days=30,
    )
    db.add_all(
        [
            business,
            portfolio,
            program,
            department,
            project,
            person,
            metric,
            objective,
            m.ScorecardContribution(
                project=project,
                objective=objective,
                contribution_type="direct",
                rationale="The delivery improves quality gates.",
            ),
            scorecard_metric,
            m.ScorecardMetricObservation(
                metric_definition=scorecard_metric,
                observed_on=date(2026, 3, 31),
                value=1,
                evidence_note="Quality review",
            ),
        ]
    )
    db.commit()

    response = client.get("/org/configuration")

    assert response.status_code == 200
    assert "Organization configuration" in response.text
    for label in (
        "1 business",
        "1 portfolio",
        "1 program",
        "1 project",
        "1 department",
        "1 person",
        "1 quality metric",
        "1 strategic objective",
        "1 metric definition",
        "1 metric observation",
        "1 scorecard contribution",
        "0 scorecard source",
    ):
        assert label in response.text
    for path in (
        "POST /businesses",
        "POST /portfolios",
        "POST /programs",
        "POST /projects",
        "POST /departments",
        "POST /people",
        "POST /quality-metrics",
        "POST /scorecard-sources",
    ):
        assert path in response.text
    assert 'href="/org/departments"' in response.text
    assert "Balanced operating readiness" in response.text
    assert "Strategy objectives" in response.text
    assert "Metric evidence" in response.text
    assert "Ready" in response.text


def test_empty_configuration_exposes_missing_layers(client: TestClient) -> None:
    response = client.get("/org/configuration")

    assert response.status_code == 200
    assert response.text.count("Needs setup") >= 5
    assert "POST /strategic-objectives" in response.text


def test_tailoring_rows_count_every_control_under_exactly_one_mode() -> None:
    """The three counts are walked over every ``ControlMode``, never one counted
    field with the rest folded into "everything else" — so each profile's three
    counts sum to exactly its own Monitoring & Controlling control count, and an
    ``OPERATIONS_CADENCE`` control can never land silently inside
    ``predictive_count``."""
    mc_count = len(catalog.by_group(ProcessGroup.MONITORING))
    rows = _tailoring_rows()
    assert {row["key"] for row in rows} == set(tailoring.PROFILES)
    for row in rows:
        predictive = cast(int, row["predictive_count"])
        adaptive = cast(int, row["adaptive_count"])
        operations = cast(int, row["operations_count"])
        assert predictive + adaptive + operations == mc_count, row["key"]

    operations_row = next(row for row in rows if row["key"] == "operations")
    assert operations_row["operations_count"] == mc_count - 2  # 4.5/4.6 stay predictive
    assert operations_row["adaptive_count"] == 0


def test_configuration_page_renders_the_operations_cadence_column(client: TestClient) -> None:
    response = client.get("/org/configuration")

    assert response.status_code == 200
    assert "On the department's own cadence" in response.text
