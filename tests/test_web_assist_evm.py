"""The earned-value calculator page: ``GET /projects/{id}/assist/earned-value``.

Same worked numbers as ``tests/test_web_pages.py``'s overspend seed (BAC 1,000, 20%
done, AC 800 as of 2026-03-31): CPI 0.25, EAC 4,000, TCPI-to-BAC 4.0, TCPI-to-EAC
0.25 — hand-computed so a reviewer can check them without running anything.
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
    Baseline,
    BaselineLine,
    Business,
    CostEntry,
    Portfolio,
    Project,
    Task,
    Workstream,
)

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


def test_the_page_shows_the_same_figures_the_hub_shows(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/earned-value{Q}").text
    assert body.count(">1,000<") or "1,000" in body  # BAC
    assert ">200<" in body  # EV
    assert ">800<" in body  # AC
    assert "0.25" in body  # CPI
    assert "4,000" in body  # EAC
    assert "-3,000" in body  # VAC


def test_tcpi_is_computed_both_ways(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/earned-value{Q}").text
    assert "4.0" in body  # to_bac = (1000-200)/(1000-800)
    assert "0.25" in body  # to_eac = (1000-200)/(4000-800)


def test_the_page_carries_a_plain_interpretation(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/earned-value{Q}").text
    assert "You have spent more than the work you finished is worth" in body


def test_the_what_if_input_recomputes_without_writing(client: TestClient, db: Session) -> None:
    before = db.query(CostEntry).count()
    resp = client.get(f"/projects/1/assist/earned-value{Q}&whatif_remaining_cost=1000")
    assert resp.status_code == 200
    body = resp.text
    assert "1,800" in body  # what-if EAC = AC 800 + remaining 1000
    assert db.query(CostEntry).count() == before  # nothing written


def test_the_what_if_cpi_input_recomputes_without_writing(client: TestClient, db: Session) -> None:
    before = db.query(CostEntry).count()
    resp = client.get(f"/projects/1/assist/earned-value{Q}&whatif_cpi=0.5")
    assert resp.status_code == 200
    body = resp.text
    assert "2,000" in body  # what-if EAC = BAC 1000 / CPI 0.5
    assert "-1,000" in body  # what-if VAC = BAC 1000 - EAC 2000
    assert "You have spent more than the work you finished is worth" in body
    assert db.query(CostEntry).count() == before  # nothing written


def test_the_page_carries_its_provenance(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/earned-value{Q}").text
    assert "Earned Value Analysis" in body
    assert "7.4" in body
    assert AS_OF.isoformat() in body


def test_the_page_links_to_the_one_change_boundary(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/earned-value{Q}").text
    assert "Raise a change request" in body
    assert "/projects/1/raid#changes" in body
    assert "7.4" in body  # the origin process, in the change-boundary line


def test_the_page_shows_earned_schedule_beside_spi(client: TestClient) -> None:
    # ES 18.0, AT 90, PD 90 (task fully accrued at as_of): SPI(t) = 18/90 = 0.2,
    # SV(t) = 18-90 = -72, IEAC(t) = 90/0.2 = 450 — hand-computed off the same
    # single-task baseline/progress the other tests here use.
    body = client.get(f"/projects/1/assist/earned-value{Q}").text
    assert 'id="evm-es">18.0<' in body
    assert 'id="evm-at">90<' in body
    assert 'id="evm-pd">90<' in body
    assert 'id="evm-spi-t">0.2<' in body
    assert 'id="evm-sv-t">-72.0<' in body
    assert 'id="evm-ieac-t">450.0<' in body


def test_the_page_shows_cv_sv_and_every_eac_method_side_by_side(client: TestClient) -> None:
    # CV = EV - AC = 200 - 800 = -600; SV = EV - PV = 200 - 1000 = -800 (task fully accrued).
    body = client.get(f"/projects/1/assist/earned-value{Q}").text
    assert 'id="evm-cv">-600<' in body and "over budget" in body
    assert 'id="evm-sv">-800<' in body and "behind plan" in body
    for method_id in ("cpi", "remaining_at_plan", "remaining_at_current", "bottom_up"):
        assert f'id="eac-method-{method_id}"' in body
    # cpi: BAC/CPI = 1000/0.25 = 4000; remaining_at_plan: AC + (BAC - EV) = 800 + 800 = 1600
    assert 'id="eac-value-cpi">4,000<' in body
    assert 'id="eac-value-remaining_at_plan">1,600<' in body
    assert 'id="eac-value-bottom_up">no data yet<' in body  # no re-estimate supplied yet

    # The method selector picks up a bottom-up what-if: AC 800 + supplied 500 = 1300.
    picked = client.get(
        f"/projects/1/assist/earned-value{Q}&whatif_remaining_cost=500&method=bottom_up"
    ).text
    assert 'id="eac-value-bottom_up">1,300<' in picked
    assert '<option value="bottom_up" selected>' in picked


def test_an_unknown_project_404s(client: TestClient) -> None:
    assert client.get(f"/projects/999/assist/earned-value{Q}").status_code == 404


def test_the_reference_card_renders_collapsed_after_the_computed_cards(
    client: TestClient,
) -> None:
    """Outcome-first ordering: the computed EVM cards stay open ``<section>``s,
    the "Where this comes from" reference card collapses beneath them rather
    than competing with the figures a reader came for."""
    body = client.get(f"/projects/1/assist/earned-value{Q}").text
    where_from = body.index("<summary><h2>Where this comes from</h2>")
    where_stands = body.index("Where the project stands")
    assert where_stands < where_from
    assert '<details class="card assist-card">' in body
    assert body.count('<section class="card assist-card">') >= 3


def test_the_recommended_action_now_launches_here_instead_of_only_explaining(
    db: Session,
) -> None:
    from driftless.assess import engine as assess

    cost = {a.kind: a for a in assess.assess_project(db, db.get(Project, 1), AS_OF)}["cost"]
    eva = next(a for a in cost.actions if a.pmbok_tt == "earned_value_analysis")
    assert eva.launch_href == "/projects/1/assist/earned-value"
    assert eva.is_reference_only is False


def test_cpi_interpretation_at_exactly_on_plan() -> None:
    from driftless.web.assist_evm import _cpi_interpretation

    assert _cpi_interpretation(1.0) == (
        "Spend and the value of finished work are exactly in balance."
    )


def test_action_launch_href_formats_in_the_one_place_the_model_owns() -> None:
    action = Action("probe", "label", "earned_value_analysis", "why", "project:42")
    assert action.launch_href == "/projects/42/assist/earned-value"
    assert (
        model.ASSISTANT_ROUTES["earned_value_analysis"]
        == "/projects/{project_id}/assist/earned-value"
    )


def test_launch_href_is_none_for_a_target_ref_that_names_no_project() -> None:
    """A routed technique whose ``target_ref`` does not start with ``project:``
    (a portfolio- or programme-scoped action, say) cannot fill the route's
    ``{project_id}`` — ``launch_href`` says so with ``None`` rather than a
    half-filled or wrong address."""
    portfolio_scoped = Action("probe", "label", "earned_value_analysis", "why", "portfolio:7")
    assert portfolio_scoped.launch_href is None
    malformed = Action("probe", "label", "earned_value_analysis", "why", "project:")
    assert malformed.launch_href is None
