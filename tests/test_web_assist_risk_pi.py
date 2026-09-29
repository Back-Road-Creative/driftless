"""The P x I scoring page: ``GET /projects/{id}/assist/risk-pi``."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.assess.model import ASSISTANT_ROUTES
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.models import Business, Portfolio, Project, Risk
from driftless.pmbok.reasons import GUIDE_ONLY_REASONS
from driftless.web.assist_risk_pi import _impact_scale, _rows

AS_OF = date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"


def _seed(session: Session) -> Project:
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    session.add(project)
    session.commit()
    return project


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


def test_the_route_is_registered_and_the_reason_is_gone() -> None:
    key = "risk_probability_and_impact_assessment"
    assert ASSISTANT_ROUTES[key] == "/projects/{project_id}/assist/risk-pi"
    assert key not in GUIDE_ONLY_REASONS


def test_the_page_renders_with_no_open_risks(client: TestClient) -> None:
    resp = client.get(f"/projects/1/assist/risk-pi{Q}")
    assert resp.status_code == 200
    assert "No open risks" in resp.text


def test_an_unknown_project_404s(client: TestClient) -> None:
    assert client.get(f"/projects/999/assist/risk-pi{Q}").status_code == 404


def _risk(project: Project, desc: str, prob: float, impact: float, status: str = "open") -> Risk:
    return Risk(project=project, description=desc, probability=prob, impact=impact, status=status)


def test_the_page_ranks_open_risks_and_hides_closed_ones(db: Session, client: TestClient) -> None:
    project = db.get(Project, 1)
    assert project is not None
    db.add_all(
        [
            _risk(project, "vendor", 0.4, 1_000.0),
            _risk(project, "scope", 0.9, 9_000.0),
            _risk(project, "mothballed", 0.9, 9_000.0, status="closed"),
        ]
    )
    db.commit()
    resp = client.get(f"/projects/1/assist/risk-pi{Q}")
    assert resp.status_code == 200
    assert "mothballed" not in resp.text
    # higher probability and impact -> higher score -> ranks first.
    assert resp.text.index("scope") < resp.text.index("vendor")


# --- calculation unit tests: hand-computed expected numbers -----------------


def test_impact_scale_spans_the_register_s_own_range() -> None:
    # 5 equal bands over [10_000, 50_000]: width 8_000 each.
    scale = _impact_scale([10_000.0, 20_000.0, 50_000.0])
    assert scale.level_for(10_000.0).name == "very_low"
    assert scale.level_for(50_000.0).name == "very_high"
    assert scale.level_for(30_000.0).name == "moderate"


def test_impact_scale_handles_a_single_repeated_value() -> None:
    assert _impact_scale([5_000.0, 5_000.0]).level_for(5_000.0).name == "very_low"


def test_rows_scores_each_open_risk_by_probability_times_impact_band(db: Session) -> None:
    project = db.get(Project, 1)
    assert project is not None
    # 0.1 -> very_low(1) x register-min impact -> very_low(1): score 1, band low.
    # 0.95 -> very_high(5) x register-max impact -> very_high(5): score 25, band high.
    db.add_all([_risk(project, "low", 0.1, 1_000.0), _risk(project, "high", 0.95, 100_000.0)])
    db.commit()
    by_description = {row["risk"].description: row for row in _rows(db, project)}
    assert (by_description["low"]["score"], by_description["low"]["band"]) == (1, "low")
    assert (by_description["high"]["score"], by_description["high"]["band"]) == (25, "high")


def _provenance_card(body: str) -> str:
    """Just the "Where this comes from" card, so an as-of printed elsewhere on the
    page (the header line) cannot be mistaken for one printed inside the card."""
    start = body.index("<summary><h2>Where this comes from</h2>")
    return body[start : body.index("</details>", start)]


def test_the_page_carries_its_provenance(client: TestClient) -> None:
    card = _provenance_card(client.get(f"/projects/1/assist/risk-pi{Q}").text)
    assert "Risk Probability and Impact Assessment" in card
    assert "11.3" in card
    assert "Perform Qualitative Risk Analysis" in card


def test_the_provenance_card_prints_no_as_of(client: TestClient) -> None:
    """``Risk`` carries no date column, so ``at`` filters nothing this page reads
    (``_rows`` is not even passed it). An as-of line here would show the reader a
    date that changes nothing, so the card cites the process and technique only."""
    card = _provenance_card(client.get(f"/projects/1/assist/risk-pi{Q}").text)
    assert AS_OF.isoformat() not in card
    assert "as of" not in card.lower()
