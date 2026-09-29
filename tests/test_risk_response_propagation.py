"""A filed ``RiskResponse`` reaches every consumer the plan declared for it — proved by
actually filing one and reading each consumer before and after, never by inspecting
source for a call site.

One seeded project, one open risk, one response filed through
``driftless.services.risk_writes.file_risk_response`` — the same boundary the web page
and the JSON route both use — and five reads: the residual-exposure adapter itself,
the project hub's reserve line, the gantt page's schedule note, the threat board's
risk description, and the risk-register report. The scorecard family has no derived
metric type (``driftless.models.scorecard.METRIC_SOURCE_TYPES`` is ``manual`` /
``registered_connector`` only), so risk exposure cannot feed it as an observation
without a manual entry a human types — nothing here claims that consumer.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api import schemas as s
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.assess.evaluators import risk as risk_evaluator
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.pmbok import risk_facts
from driftless.report import render_document
from driftless.services.risk_writes import file_risk_response

AS_OF = date(2026, 3, 31)
JAN = date(2026, 1, 1)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as session:
        yield session


@pytest.fixture
def project(db: Session) -> m.Project:
    """A budgeted, under-reserved project with one open, unanswered risk."""
    portfolio = m.Portfolio(name="Content", business=m.Business(name="BRC"))
    proj = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="Post", project=proj)
    task = m.Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = m.Baseline(project=proj, version=1, status="approved")
    line = m.BaselineLine(
        baseline=baseline, task=task, planned_cost=10_000.0, planned_start=JAN, planned_finish=AS_OF
    )
    db.add(line)
    db.add(m.CostEntry(project=proj, category="labour", incurred_on=JAN, amount=1_000.0))
    db.add(m.BudgetLine(project=proj, category="contingency", planned_amount=100.0))
    db.add(
        m.Risk(
            project=proj,
            description="Vendor outage",
            probability=0.8,
            impact=5000.0,  # exposure 4000, well past the 100 contingency: red
            status="open",
            kind="threat",
        )
    )
    db.add(m.Person(name="Priya"))
    db.commit()
    return proj


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def _file_response(db: Session, project: m.Project) -> None:
    risk = db.scalars(select(m.Risk).where(m.Risk.project_id == project.id)).one()
    owner = db.scalars(select(m.Person)).one()
    payload = s.RiskResponseIn(
        project_id=project.id,
        risk_id=risk.id,
        strategy="mitigate",
        owner_id=owner.id,
        trigger="Outage exceeds four hours",
        planned_action="Fail over to the secondary vendor",
        residual_probability=0.1,
        residual_impact=200.0,  # residual exposure 20, far below the raw 4000
        cost_of_response=500.0,  # exceeds the 100 contingency: change-control link
        schedule_days=3,
        status="planned",
        actor="pm",
        as_of=AS_OF,
    )
    file_risk_response(db, payload)


def test_residual_exposure_drops_once_a_response_is_filed(db: Session, project: m.Project) -> None:
    before = risk_facts.gather(db, project, AS_OF)
    assert before.residual_exposure == pytest.approx(4000.0)
    assert before.unanswered_risk_ids

    _file_response(db, project)

    after = risk_facts.gather(db, project, AS_OF)
    assert after.residual_exposure == pytest.approx(20.0)
    assert after.responded_schedule_days == 3
    assert after.responded_cost == pytest.approx(500.0)
    assert not after.unanswered_risk_ids


def test_the_cost_workbench_reserve_line_moves_with_it(
    client: TestClient, db: Session, project: m.Project
) -> None:
    q = f"?as_of={AS_OF.isoformat()}"
    before = client.get(f"/projects/{project.id}/hub{q}")
    assert before.status_code == 200
    assert "4,000.00" in before.text

    _file_response(db, project)

    after = client.get(f"/projects/{project.id}/hub{q}")
    assert after.status_code == 200
    assert "20.00" in after.text


def test_the_gantt_schedule_note_appears_only_once_a_response_carries_days(
    client: TestClient, db: Session, project: m.Project
) -> None:
    q = f"?as_of={AS_OF.isoformat()}"
    before = client.get(f"/projects/{project.id}/gantt{q}")
    assert before.status_code == 200
    assert "risk-schedule-note" not in before.text

    _file_response(db, project)

    after = client.get(f"/projects/{project.id}/gantt{q}")
    assert after.status_code == 200
    assert "risk-schedule-note" in after.text and "3" in after.text


def test_the_threat_boards_no_response_note_clears_once_filed(
    db: Session, project: m.Project
) -> None:
    before = risk_evaluator.evaluate(db, project, AS_OF)
    assert "No response planned" in before.threats[0].description

    _file_response(db, project)

    after = risk_evaluator.evaluate(db, project, AS_OF)
    assert not after.threats or "No response planned" not in after.threats[0].description
    assert after.risk_score <= before.risk_score


def test_the_risk_report_lists_the_filed_response(db: Session, project: m.Project) -> None:
    before = render_document("risk-register", db, project, AS_OF)
    assert "Priya" not in before

    _file_response(db, project)

    after = render_document("risk-register", db, project, AS_OF)
    assert "Priya" in after and "Fail over to the secondary vendor" in after


def test_a_response_over_contingency_links_to_raise_a_change_request(
    client: TestClient, db: Session, project: m.Project
) -> None:
    _file_response(db, project)  # cost_of_response 500 > the 100 contingency held
    page = client.get(f"/projects/{project.id}/assist/risk-responses?as_of={AS_OF.isoformat()}")
    assert page.status_code == 200
    assert "Raise a change request" in page.text
