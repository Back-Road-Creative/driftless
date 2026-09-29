"""The cost workbench page: ``GET /projects/{id}/assist/cost``.

Same seed shape as ``tests/test_web_assist_evm.py`` (BAC 1,000 planned JAN->AS_OF, AC
800) plus two budget lines (labour 900, contingency 100) and a second project's own
spend, so every section's numbers are hand-computable from the module docstring's
description rather than merely "some number rendered".
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.assess import model
from driftless.assess.model import Action
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.models import (
    Baseline,
    EstimateScenario,
    BaselineLine,
    Business,
    BudgetLine,
    CostEntry,
    Portfolio,
    Project,
    Task,
    Workstream,
)
from driftless.web.assist_cost import _historical_reference

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"


def _seed(session: Session) -> None:
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = Baseline(project=project, version=1, status="approved")
    line = BaselineLine(
        baseline=baseline, task=task, planned_cost=1000.0, planned_start=JAN, planned_finish=AS_OF
    )
    session.add(line)
    session.add(CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    session.add(BudgetLine(project=project, category="labour", planned_amount=900.0))
    session.add(BudgetLine(project=project, category="contingency", planned_amount=100.0))
    other = Project(name="Watchtower", portfolio=project.portfolio, delivery_mode="predictive")
    session.add(other)
    session.add(CostEntry(project=other, category="labour", incurred_on=JAN, amount=450.0))
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


def test_cost_aggregation_rolls_up_budget_lines_by_category(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/cost{Q}").text
    assert "labour" in body and "900.00" in body
    assert "contingency" in body and "100.00" in body
    assert "1,000.00" in body  # project total


def test_reserve_analysis_what_if(client: TestClient) -> None:
    resp = client.get(f"/projects/1/assist/cost{Q}&contingency_pct=0.1&management_pct=0.05")
    assert resp.status_code == 200
    body = resp.text
    assert "90.00" in body  # contingency reserve = 900 * 0.1
    assert "990.00" in body  # cost baseline = 900 + 90
    assert "49.50" in body  # management reserve = 990 * 0.05
    assert "1,039.50" in body  # total budget = 990 + 49.5


def test_the_cash_flow_s_curve_renders_the_fully_accrued_baseline(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/cost{Q}").text
    assert '<svg class="scurve" viewBox="0 0 320 140"' in body
    assert "1,000.00" in body  # fully accrued by the as-of date


def test_funding_limit_reconciliation_breaches_a_low_limit_on_the_as_of_period(
    client: TestClient,
) -> None:
    resp = client.get(f"/projects/1/assist/cost{Q}&limit=2026-03-31:1")
    assert resp.status_code == 200
    body = resp.text
    # The 12-way sampled sum rounds a cent above the true 1000.0 total; the
    # breach's own arithmetic (cumulative - limit) is what is pinned here, not
    # the exact float.
    assert "1,000.01" in body
    assert "999.01" in body


def test_funding_limit_reconciliation_clears_a_high_limit(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/cost{Q}&limit=2026-03-31:5000").text
    assert "No period breaches the limits given." in body


def test_financing_what_if(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/cost{Q}&financing_principal=1000&financing_rate=0.1"
        "&financing_periods=2&financing_method=simple"
    )
    assert resp.status_code == 200
    assert "200.00" in resp.text  # 1000 * 0.1 * 2


def test_run_rate_averages_recorded_spend(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/cost{Q}").text
    assert "800.00" in body  # one bucketed month of AC


def test_cost_of_quality_what_if(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/cost{Q}&prevention=10&appraisal=20"
        "&internal_failure=5&external_failure=5"
    )
    assert resp.status_code == 200
    body = resp.text
    assert "30.00" in body  # conformance = prevention + appraisal
    assert "Prevention and appraisal spend exceeds failure costs" in body


def test_historical_information_lists_the_other_project(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/cost{Q}").text
    assert "Watchtower" in body
    assert "450.00" in body


def test_analogous_estimating_what_if(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/cost{Q}&analogous_reference_value=1000"
        "&analogous_reference_size=10&analogous_target_size=20"
    )
    assert resp.status_code == 200
    assert "2,000.00" in resp.text  # 1000 * (20/10) * 1.0


def test_parametric_estimating_what_if(client: TestClient) -> None:
    resp = client.get(f"/projects/1/assist/cost{Q}&parametric_rate=5&parametric_quantity=10")
    assert resp.status_code == 200
    assert "50.00" in resp.text


def test_three_point_estimating_what_if_defaults_to_triangular(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/cost{Q}&three_point_optimistic=6"
        "&three_point_most_likely=9&three_point_pessimistic=12"
    )
    assert resp.status_code == 200
    body = resp.text
    assert "9.00" in body  # triangular mean
    assert "range 6.00 to 12.00" in body


def test_three_point_estimating_beta_weights_the_most_likely_point(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/cost{Q}&three_point_optimistic=6"
        "&three_point_most_likely=9&three_point_pessimistic=12&three_point_method=beta"
    )
    assert resp.status_code == 200
    body = resp.text
    assert "9.00" in body  # (6 + 4*9 + 12) / 6
    assert "range 8.00 to 10.00" in body  # mean +/- 1 std dev (sigma=1.0 default)


def test_a_malformed_limit_token_is_skipped_not_500d(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/cost{Q}"
        "&limit=2026-03-31:&limit=2026-03-31:notanumber&limit=2026-03-31:5000"
    )
    assert resp.status_code == 200
    assert "No period breaches the limits given." in resp.text  # only the valid token parsed


def test_historical_information_is_empty_with_no_other_projects(tmp_path: Path) -> None:
    engine = new_engine(f"sqlite:///{tmp_path / 'solo.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as session:
        project = Project(
            name="Solo",
            portfolio=Portfolio(name="Content", business=Business(name="BRC")),
            delivery_mode="predictive",
        )
        session.add(project)
        session.commit()
        assert _historical_reference(session, project, AS_OF) == []


def test_bottom_up_estimating_what_if(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/cost{Q}&bottom_up_component_1=100&bottom_up_component_2=200"
    )
    assert resp.status_code == 200
    assert "300.00" in resp.text


def test_the_page_carries_its_provenance(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/cost{Q}").text
    assert "7.2" in body and "7.3" in body and "7.4" in body and "8.1" in body
    assert AS_OF.isoformat() in body


def test_an_unknown_project_404s(client: TestClient) -> None:
    assert client.get(f"/projects/999/assist/cost{Q}").status_code == 404


def test_the_recommended_action_now_launches_here_instead_of_only_explaining(
    db: Session,
) -> None:
    from driftless.assess import engine as assess

    project = db.get(Project, 1)
    assert project is not None
    cost = {a.kind: a for a in assess.assess_project(db, project, AS_OF)}["cost"]
    action = next(a for a in cost.actions if a.pmbok_tt == "reserve_analysis")
    assert action.launch_href == "/projects/1/assist/cost"
    assert action.is_reference_only is False


def test_action_launch_href_formats_in_the_one_place_the_model_owns() -> None:
    action = Action("probe", "label", "cost_aggregation", "why", "project:42")
    assert action.launch_href == "/projects/42/assist/cost"
    assert model.ASSISTANT_ROUTES["cost_aggregation"] == "/projects/{project_id}/assist/cost"


# --- W4.3b: the stored estimate-scenario form and the change boundary -----------


def _csrf(client: TestClient) -> str:
    page = client.get(f"/projects/1/assist/cost{Q}")
    assert page.status_code == 200
    return page.text.split('name="csrf_token" value="')[1].split('"')[0]


def test_the_page_links_to_the_one_change_boundary(client: TestClient) -> None:
    """Every figure here is a what-if; the one way any of them becomes the plan is a
    change request against Determine Budget (7.3) — the same boundary the
    earned-value page links, never a second approval path of the page's own."""
    body = client.get(f"/projects/1/assist/cost{Q}").text
    assert "Raise a change request" in body
    assert "/projects/1/raid#changes" in body
    assert "7.3" in body


def test_filing_an_estimate_scenario_stores_a_row_and_lists_it(
    client: TestClient, db: Session
) -> None:
    """The one write the page allows: filing a computed estimate as a stored
    ``EstimateScenario`` (target ``cost``), through the same validated schema the
    JSON route uses, listed back on the page with its kind, value and basis."""
    token = _csrf(client)
    resp = client.post(
        "/projects/1/assist/cost/estimate",
        data={
            "csrf_token": token,
            "as_of": AS_OF.isoformat(),
            "kind": "three_point",
            "value": "1200",
            "low": "1000",
            "high": "1500",
            "basis": "PERT over the grade estimates",
            "actor": "jp",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    assert resp.headers["location"] == f"/projects/1/assist/cost{Q}"
    stored = db.scalars(select(EstimateScenario)).all()
    assert [(row.target, row.kind, row.value, row.low, row.high, row.actor) for row in stored] == [
        ("cost", "three_point", 1200.0, 1000.0, 1500.0, "jp")
    ]
    body = client.get(f"/projects/1/assist/cost{Q}").text
    assert 'id="stored-estimates"' in body
    assert "PERT over the grade estimates" in body
    assert "1,200.00" in body


def test_a_stored_estimate_filed_for_a_later_date_stays_out_of_an_earlier_render(
    client: TestClient, db: Session
) -> None:
    db.add(
        EstimateScenario(
            project_id=1,
            target="cost",
            kind="analogous",
            value=999.0,
            basis="Filed next quarter",
            actor="jp",
            as_of=date(2026, 6, 30),
        )
    )
    db.commit()
    assert "Filed next quarter" not in client.get(f"/projects/1/assist/cost{Q}").text
    assert "Filed next quarter" in client.get("/projects/1/assist/cost?as_of=2026-06-30").text


def test_the_estimate_form_prefills_from_the_last_computed_what_if(client: TestClient) -> None:
    """A what-if just computed is the natural thing to file: the form carries the
    parametric result's own value and kind, so nothing is retyped. With no what-if
    on the request, it offers the aggregated budget as a bottom-up figure."""
    body = client.get(f"/projects/1/assist/cost{Q}&parametric_rate=12&parametric_quantity=10").text
    assert 'id="estimate-value" name="value" value="120.0"' in body
    assert '<option value="parametric" selected>' in body
    plain = client.get(f"/projects/1/assist/cost{Q}").text
    assert 'id="estimate-value" name="value" value="900.0"' in plain  # labour 900, no contingency
    assert '<option value="bottom_up" selected>' in plain


def test_a_refused_estimate_names_the_reason_and_writes_nothing(
    client: TestClient, db: Session
) -> None:
    token = _csrf(client)
    resp = client.post(
        "/projects/1/assist/cost/estimate",
        data={"csrf_token": token, "kind": "guesswork", "value": "1", "actor": "jp"},
        follow_redirects=False,
    )
    assert resp.status_code == 422
    assert db.scalars(select(EstimateScenario)).all() == []
