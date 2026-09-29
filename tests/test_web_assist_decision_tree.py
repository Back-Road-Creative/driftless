"""The decision-tree / EMV calculator: ``GET /projects/{id}/assist/decision-tree``.

A no-write what-if off GET params, the same contract ``assist_decisions``'s
voting and scoring boxes use. Worked example: the textbook well-vs-no-well
case (``tests/test_calc_risk.py``).
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
from driftless.assess.model import ASSISTANT_ROUTES
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.models import Business, Portfolio, Project
from driftless.pmbok.reasons import GUIDE_ONLY_REASONS
from driftless.web.assist_decision_tree import _arithmetic, _parse_branches
from driftless.calc.risk import DecisionBranch, Outcome

AS_OF = date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"


def _seed(session: Session) -> None:
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    session.add(project)
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


def test_the_route_is_registered_and_the_reason_is_gone() -> None:
    assert (
        ASSISTANT_ROUTES["decision_tree_analysis"] == "/projects/{project_id}/assist/decision-tree"
    )
    assert "decision_tree_analysis" not in GUIDE_ONLY_REASONS


def test_the_page_renders_with_no_options(client: TestClient) -> None:
    resp = client.get(f"/projects/1/assist/decision-tree{Q}")
    assert resp.status_code == 200
    assert "Enter at least one option" in resp.text


def test_an_unknown_project_404s(client: TestClient) -> None:
    assert client.get(f"/projects/999/assist/decision-tree{Q}").status_code == 404


def test_the_well_vs_no_well_worked_example(client: TestClient) -> None:
    resp = client.get(
        f"/projects/1/assist/decision-tree{Q}"
        "&options=drill:0.4=700000,0.6=-100000;do not drill:1.0=0"
    )
    assert resp.status_code == 200
    assert "220000.0" in resp.text  # drill's EMV
    assert "do not drill" in resp.text
    assert "drill — best option" in resp.text or "best option" in resp.text


def test_a_bad_probability_input_reports_clear_error_text(client: TestClient) -> None:
    resp = client.get(f"/projects/1/assist/decision-tree{Q}&options=bad:0.5=100")
    assert resp.status_code == 200
    assert "sum to 1" in resp.text


# --- calculation unit tests: hand-computed expected numbers -----------------


def test_parse_branches_builds_outcomes_from_the_mini_dsl() -> None:
    parsed = _parse_branches("drill:0.4=700000,0.6=-100000;do not drill:1.0=0")
    branch_by_name = {branch.name: branch for branch, error in parsed if branch is not None}
    assert branch_by_name["drill"].emv == pytest.approx(220_000.0)
    assert branch_by_name["do not drill"].emv == 0.0


def test_parse_branches_reports_the_offending_option_only() -> None:
    parsed = _parse_branches("good:1.0=5;bad:0.5=100")
    errors = {name: error for (branch, error), name in zip(parsed, ("good", "bad"), strict=True)}
    assert errors["good"] == ""
    assert "sum to 1" in errors["bad"]


def test_arithmetic_writes_out_the_emv_sum() -> None:
    branch = DecisionBranch("drill", (Outcome(0.4, 700_000.0), Outcome(0.6, -100_000.0)))
    assert _arithmetic(branch) == "0.4 x 700000.0 + 0.6 x -100000.0 = 220000.0"
