"""The department workspace: ``GET /org/departments/{id}/assist``.

Nine sections, each read off rows a single seed already carries — objectives via
this department's accountable project's active scorecard contribution, RACI
assembled from a service owner, the department itself, a stakeholder-proxy
project role and a work request's requester, demand versus capacity through the
SAME classification ``web.heatmap`` washes its grid with, service levels
through a plain average cycle time over a DONE work request, controls and
incidents, improvements, vendor agreements and project stakeholders.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import TypeVar

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.web.assist_department import create_assist_department_router

AS_OF = date(2026, 3, 31)
JAN = date(2026, 1, 1)
FEB = date(2026, 2, 1)
Q = f"?as_of={AS_OF.isoformat()}"
_PATH = "/org/departments/{}/assist"

_T = TypeVar("_T")


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(create_assist_department_router(AS_OF))
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app) as test_client:
        yield test_client


def _seed(db: Session) -> m.Department:
    business = m.Business(name="BRC")
    portfolio = m.Portfolio(name="Content Brands", business=business)
    dept = m.Department(business=business, name="Delivery")
    sam = m.Person(name="Sam", department=dept, cost_rate=90.0, capacity_hours=40.0)
    dept.people.append(sam)
    project = m.Project(
        name="GMS", portfolio=portfolio, delivery_mode="predictive", responsible_department=dept
    )
    stream = m.Workstream(name="GMS WS", project=project)
    m.Task(
        name="Grade",
        workstream=stream,
        estimate_unit="hours",
        estimate=20.0,
        status="in_progress",
        assignee=sam,
    )
    objective = m.StrategicObjective(
        business=business, perspective="financial", name="Grow revenue"
    )
    db.add(
        m.ScorecardContribution(
            project=project, objective=objective, contribution_type="direct", status="active"
        )
    )
    db.add(m.ProjectRole(project=project, role="stakeholder_proxy", holder="Robin"))
    db.add(
        m.ProcurementAgreement(project=project, vendor="Acme Studio", amount=5000.0, start_date=JAN)
    )
    db.add(
        m.Stakeholder(
            project=project, name="Dana", interest="high", influence="high", comms_cadence="weekly"
        )
    )
    service = m.DepartmentService(department=dept, name="Colour grading", owner="Ada")
    db.add(service)
    db.add(
        m.WorkRequest(
            department=dept, service=service, requester="Grace", raised_on=JAN, status="queued"
        )
    )
    db.add(
        m.WorkRequest(
            department=dept,
            service=service,
            requester="Priya",
            raised_on=JAN,
            status="done",
            started_on=JAN,
            done_on=FEB,
        )
    )
    db.add(m.RecurringWork(department=dept, name="License audit", cadence="weekly", owner="Sam"))
    db.add(
        m.ServiceLevel(department=dept, service=service, measure="turnaround_hours", target=48.0)
    )
    control = m.OperatingControl(department=dept, name="Dual approval", owner="Sam")
    db.add(control)
    db.add(m.Incident(department=dept, control=control, description="Late render", raised_on=AS_OF))
    db.add(
        m.Improvement(
            department=dept, what="Automate the license check", why="Missed once", owner="Sam"
        )
    )
    db.commit()
    return dept


def test_the_page_shows_the_objective_this_department_contributes_to(
    client: TestClient, db: Session
) -> None:
    dept = _seed(db)
    body = client.get(_PATH.format(dept.id) + Q).text
    assert body.count("Grow revenue") >= 1


def test_the_raci_row_is_assembled_from_real_rows(client: TestClient, db: Session) -> None:
    dept = _seed(db)
    body = client.get(_PATH.format(dept.id) + Q).text
    # Informed: every requester against the service, both seeded work requests — sorted.
    assert (
        '<tr class="dept-raci"><td>Colour grading</td><td>Ada</td><td>Delivery</td>'
        "<td>Robin</td><td>Grace, Priya</td></tr>" in body
    )


def test_demand_vs_capacity_reuses_the_heatmap_classification(
    client: TestClient, db: Session
) -> None:
    dept = _seed(db)
    body = client.get(_PATH.format(dept.id) + Q).text
    # Sam: 20 open hours against 40 capacity — under the heatmap's amber ratio (0.8).
    assert '<tr class="dept-demand"><td>Sam</td><td>40</td><td>20</td><td>under</td></tr>' in body


def test_service_level_shows_a_plain_average_cycle_time(client: TestClient, db: Session) -> None:
    dept = _seed(db)
    body = client.get(_PATH.format(dept.id) + Q).text
    # Priya's request: raised JAN 1, done FEB 1 — 31 days, the only completed item.
    assert "31.0 days average over 1 completed item" in body


def test_controls_and_incidents_shows_the_open_count_and_worst_severity(
    client: TestClient, db: Session
) -> None:
    dept = _seed(db)
    body = client.get(_PATH.format(dept.id) + Q).text
    # The one open medium-severity incident is dated the page's own as-of (AS_OF):
    # amber for "open incident, not high/critical", 0 days of evidence age.
    assert (
        '<tr class="dept-control"><td>Dual approval</td><td>Sam</td><td>1</td><td>medium</td>'
        '<td class="rag amber">amber</td><td>0</td><td>1 open incident(s)</td></tr>' in body
    )


def test_a_high_severity_open_incident_makes_the_control_red(
    client: TestClient, db: Session
) -> None:
    dept = _seed(db)
    hot = m.OperatingControl(department=dept, name="Access review", owner="Sam")
    db.add(hot)
    db.add(
        m.Incident(
            department=dept,
            control=hot,
            description="Unauthorized access",
            severity="critical",
            raised_on=AS_OF,
        )
    )
    db.commit()
    body = client.get(_PATH.format(dept.id) + Q).text
    assert (
        '<td>Access review</td><td>Sam</td><td>1</td><td>critical</td><td class="rag red">red</td>'
        in body
    )


def test_a_control_with_no_incidents_reads_amber_for_no_evidence(
    client: TestClient, db: Session
) -> None:
    dept = _seed(db)
    quiet = m.OperatingControl(department=dept, name="Backup verification", owner="Sam")
    db.add(quiet)
    db.commit()
    body = client.get(_PATH.format(dept.id) + Q).text
    assert (
        "<td>Backup verification</td><td>Sam</td><td>0</td><td>—</td>"
        '<td class="rag amber">amber</td><td>no evidence yet</td><td>no evidence yet</td>' in body
    )


def test_a_resolved_incident_with_fresh_evidence_and_no_open_incident_is_green(
    client: TestClient, db: Session
) -> None:
    dept = _seed(db)
    clean = m.OperatingControl(department=dept, name="Change approval", owner="Sam")
    db.add(clean)
    db.add(
        m.Incident(
            department=dept,
            control=clean,
            description="Past issue",
            severity="low",
            status="resolved",
            raised_on=JAN,
            resolved_on=AS_OF,
        )
    )
    db.commit()
    body = client.get(_PATH.format(dept.id) + Q).text
    assert (
        "<td>Change approval</td><td>Sam</td><td>0</td><td>—</td>"
        '<td class="rag green">green</td><td>0</td>' in body
    )


def test_vendors_and_stakeholders_read_off_accountable_projects(
    client: TestClient, db: Session
) -> None:
    dept = _seed(db)
    body = client.get(_PATH.format(dept.id) + Q).text
    assert (
        '<tr class="dept-vendor"><td>Acme Studio</td><td>GMS</td><td>5,000.00</td><td>draft</td></tr>'
        in body
    )
    assert (
        '<tr class="dept-stakeholder"><td>Dana</td><td>GMS</td><td>high</td><td>high</td><td>weekly</td></tr>'
        in body
    )


def test_an_unknown_department_id_is_404(client: TestClient) -> None:
    assert client.get(_PATH.format(999) + Q).status_code == 404


def test_a_pinned_as_of_renders_byte_identically(client: TestClient, db: Session) -> None:
    dept = _seed(db)
    first = client.get(_PATH.format(dept.id) + Q).text
    second = client.get(_PATH.format(dept.id) + Q).text
    assert first == second


def test_the_department_detail_page_links_to_the_workspace(db: Session) -> None:
    dept = _seed(db)
    real_app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(real_app) as client:
            page = client.get(f"/org/departments/{dept.id}{Q}")
            assert page.status_code == 200, page.text
            assert f'href="/org/departments/{dept.id}/assist{Q}"' in page.text
            workspace = client.get(f"/org/departments/{dept.id}/assist{Q}")
            assert workspace.status_code == 200, workspace.text
            assert workspace.headers["content-type"].startswith("text/html")
    finally:
        real_app.dependency_overrides.clear()


@pytest.fixture
def n1_store(tmp_path: Path) -> Iterator[tuple[Engine, sessionmaker[Session], int]]:
    """One department with several accountable projects, each carrying a vendor
    agreement and a stakeholder, so an un-batched per-project read shows up as
    an N+1 statement count."""
    engine = new_engine(f"sqlite:///{tmp_path / 'n1_assist_department.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as db:
        business = m.Business(name="BRC")
        portfolio = m.Portfolio(name="Content Brands", business=business)
        dept = m.Department(business=business, name="Delivery")
        db.add(dept)
        for j in range(8):
            project = m.Project(
                name=f"Project {j}",
                portfolio=portfolio,
                delivery_mode="predictive",
                responsible_department=dept,
            )
            db.add(m.ProcurementAgreement(project=project, vendor=f"Vendor {j}", start_date=JAN))
            db.add(m.Stakeholder(project=project, name=f"Stakeholder {j}"))
        db.commit()
        dept_id = dept.id
    yield engine, factory, dept_id


def _cold_client(factory: sessionmaker[Session]) -> TestClient:
    app = FastAPI()
    app.include_router(create_assist_department_router(AS_OF))

    def cold_session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = cold_session
    return TestClient(app)


def _count_statements(engine: Engine, call: Callable[[], _T]) -> tuple[_T, int]:
    counter = {"n": 0}

    def _bump(*_: object) -> None:
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _bump)
    try:
        result = call()
    finally:
        event.remove(engine, "before_cursor_execute", _bump)
    return result, counter["n"]


# Measured at 8 projects, one vendor agreement and one stakeholder apiece: a flat handful
# of statements — one per collection this page reads, never one per project. Re-derived at
# measured + 3 so a per-project un-batching (vendors or stakeholders read off a lazy
# ``project.procurement_agreements``/``project.stakeholders`` instead of the eager-loaded
# query) trips it well before it could hide below the ceiling.
# +2 for W4.3b's budget section: the department's own budget lines and the cost
# entries of its accountable projects, one batched statement each.
_MAX_STMTS = 17


def test_the_page_stays_under_the_statement_ceiling(
    n1_store: tuple[Engine, sessionmaker[Session], int],
) -> None:
    engine, factory, dept_id = n1_store
    client = _cold_client(factory)
    response, stmts = _count_statements(engine, lambda: client.get(_PATH.format(dept_id) + Q))
    assert response.status_code == 200, response.text
    assert stmts <= _MAX_STMTS, (
        f"{_PATH} ran {stmts} statements (ceiling {_MAX_STMTS}): a per-project vendor or "
        "stakeholder read is loading lazily again"
    )


def test_budget_and_run_rate_read_the_departments_own_lines_and_its_projects_spend(
    client: TestClient, db: Session
) -> None:
    """W4.3b: the department's own budget lines (``BudgetLine.department_id``) rolled
    up by category, beside the run rate of spend on the projects it is accountable
    for — the same trailing-window average the project cost workbench prints, over
    the department's projects together rather than one at a time."""
    dept = _seed(db)
    project = db.scalars(select(m.Project)).one()
    db.add(m.BudgetLine(department=dept, category="labour", planned_amount=4000.0))
    db.add(m.BudgetLine(department=dept, category="materials", planned_amount=500.0))
    db.add(m.CostEntry(project=project, category="labour", incurred_on=FEB, amount=300.0))
    db.add(m.CostEntry(project=project, category="labour", incurred_on=AS_OF, amount=600.0))
    db.commit()
    body = client.get(_PATH.format(dept.id) + Q).text
    assert 'id="budget-total">4,500.00<' in body
    assert "labour" in body and "materials" in body
    # Two months carry spend (Feb 300, Mar 600); ``calc.cost.run_rate`` averages the
    # periods that exist inside its window — 450.00/month, never a zero-padded 300.
    assert 'id="run-rate">450.00<' in body


def test_budget_and_run_rate_render_their_empty_states_with_nothing_filed(
    client: TestClient, db: Session
) -> None:
    dept = _seed(db)
    body = client.get(_PATH.format(dept.id) + Q).text
    assert 'id="budget-empty"' in body
    assert 'id="run-rate-empty"' in body


def test_the_page_opens_with_a_summary_strip_and_renders_its_sections_as_cards(
    client: TestClient, db: Session
) -> None:
    """D.4: the same one assistant-page shape every ``assist_*.html`` draws
    through ``_assist.html``'s macros — a headline ``.tiles.assist-summary``
    strip, then every section as its own ``.card.assist-card``."""
    dept = _seed(db)
    body = client.get(_PATH.format(dept.id) + Q).text
    assert 'class="tiles assist-summary"' in body
    assert body.count('class="card assist-card"') >= 9
