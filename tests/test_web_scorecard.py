"""The scorecard page exposes every perspective and honest evidence states."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.web.scorecard import create_scorecard_router

AS_OF = date(2026, 8, 12)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(create_scorecard_router(AS_OF))
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


def test_scorecard_keeps_all_four_perspectives_and_evidence_states(
    client: TestClient, db: Session
) -> None:
    business = m.Business(name="Northstar")
    financial = m.StrategicObjective(
        business=business, perspective="financial", name="Sustain margin"
    )
    customer = m.StrategicObjective(
        business=business, perspective="customer_stakeholder", name="Retain customers"
    )
    metric = m.ScorecardMetricDefinition(
        objective=financial,
        name="Operating margin",
        direction="higher_is_better",
        unit="percent",
        target_value=20,
        amber_threshold=15,
        red_threshold=10,
        cadence_days=30,
    )
    red_metric = m.ScorecardMetricDefinition(
        objective=financial,
        name="Escaped defects",
        direction="lower_is_better",
        unit="count",
        target_value=1,
        amber_threshold=2,
        red_threshold=4,
        cadence_days=30,
    )
    portfolio = m.Portfolio(name="Delivery", business=business)
    project = m.Project(name="Margin rollout", portfolio=portfolio)
    contribution = m.ScorecardContribution(
        project=project,
        objective=financial,
        contribution_type="direct",
        rationale="Closes the margin leak.",
    )
    db.add_all(
        [
            business,
            financial,
            customer,
            metric,
            portfolio,
            project,
            contribution,
            m.ScorecardMetricObservation(
                metric_definition=metric,
                observed_on=AS_OF,
                value=21,
                evidence_note="Month-end close",
            ),
            m.ScorecardMetricObservation(
                metric_definition=red_metric,
                observed_on=AS_OF,
                value=5,
                evidence_note="Quality review",
            ),
        ]
    )
    db.commit()

    response = client.get("/scorecard?as_of=2026-08-12")

    assert response.status_code == 200
    for label in (
        "Financial",
        "Customer &amp; Stakeholder",
        "Internal Operations",
        "People &amp; Capability",
    ):
        assert label in response.text
    assert "Sustain margin" in response.text
    assert "Supporting projects: Margin rollout" in response.text
    assert "green" in response.text
    assert "Escaped defects" in response.text
    assert re.search(r"red.*?Sustain margin", response.text, re.DOTALL)
    assert "Retain customers" in response.text
    assert "unknown" in response.text
    assert "No objective configured" in response.text
    assert "As of 2026-08-12" in response.text


def test_empty_scorecard_explains_how_to_start(client: TestClient) -> None:
    response = client.get("/scorecard")

    assert response.status_code == 200
    assert "Balanced scorecard" in response.text
    assert "No strategic objectives configured" in response.text
    assert "POST /strategic-objectives" in response.text
