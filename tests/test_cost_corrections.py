"""A wrong ``CostEntry`` is corrected by a reversing negative row plus a new correct
row (see docs/temporal-model.md), never an edit -- so ``amount`` must accept a
negative, and does so alongside every other test here at both the layers the old
``amount >= 0`` rule lived at: the Pydantic schema (``CostEntryIn``) and the DB
``CheckConstraint`` (``ck_cost_entry_amount``). What replaces it is a symmetric
sanity range, not an unbounded field -- ``driftless.models.records.
COST_ENTRY_AMOUNT_BOUND`` -- so a magnitude data-entry error still 422s / IntegrityErrors.
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from driftless.api.app import app, get_session
from driftless.api.schemas import CostEntryIn
from driftless.calc import evm
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business, CostEntry, Portfolio, Project
from driftless.models.records import COST_ENTRY_AMOUNT_BOUND

INCURRED, CORRECTED_ON, AS_OF = date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 31)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


@pytest.fixture
def project(session: Session) -> Project:
    portfolio = Portfolio(name="Content Brands", business=Business(name="Back Road Creative"))
    project = Project(name="GoMoveShift 2026", portfolio=portfolio)
    session.add(project)
    session.commit()
    return project


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    made = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with made() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _project_via_api(client: TestClient) -> int:
    business = client.post("/businesses", json={"name": "Back Road Creative"}).json()["id"]
    portfolio = client.post(
        "/portfolios", json={"name": "Content Brands", "business_id": business}
    ).json()["id"]
    response = client.post(
        "/projects",
        json={"name": "GMS", "portfolio_id": portfolio, "delivery_mode": "predictive"},
    )
    return int(response.json()["id"])


def test_schema_accepts_a_reversing_negative_row() -> None:
    """This is the whole point: a negative amount used to 422 and no longer does."""
    entry = CostEntryIn(project_id=1, category="labour", incurred_on=INCURRED, amount=-250.0)
    assert entry.amount == -250.0


def test_api_accepts_a_reversing_negative_row(client: TestClient) -> None:
    project = _project_via_api(client)
    response = client.post(
        "/cost-entries",
        json={
            "project_id": project,
            "category": "labour",
            "incurred_on": INCURRED.isoformat(),
            "amount": -250.0,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["amount"] == -250.0


def test_reversal_plus_correction_sums_to_the_corrected_figure(
    session: Session, project: Project
) -> None:
    """Wrong: 250.0. Corrected: 400.0. A reader summing AC(t) at an as-of after
    both extra rows land must see 400.0, not 650.0 and not 250.0 -- through the
    real ``driftless.calc.evm.actual_cost`` path, not a hand-rolled sum."""
    wrong = CostEntry(project=project, category="labour", incurred_on=INCURRED, amount=250.0)
    reversal = CostEntry(
        project=project, category="labour", incurred_on=CORRECTED_ON, amount=-250.0
    )
    correct = CostEntry(project=project, category="labour", incurred_on=CORRECTED_ON, amount=400.0)
    session.add_all([wrong, reversal, correct])
    session.commit()

    rows = session.query(CostEntry).all()
    costs = [evm.CostEntry(incurred_on=row.incurred_on, amount=row.amount) for row in rows]
    assert evm.actual_cost(costs, AS_OF) == pytest.approx(400.0)
    # And the store never held two disagreeing totals for a date after both corrections land.
    assert evm.actual_cost(costs, INCURRED) == pytest.approx(250.0), "before the correction"


def test_ordinary_positive_cost_still_works(session: Session, project: Project) -> None:
    entry = CostEntry(project=project, category="labour", incurred_on=INCURRED, amount=400.0)
    session.add(entry)
    session.commit()

    stored = session.get(CostEntry, entry.id)
    assert stored is not None and stored.amount == 400.0


@pytest.mark.parametrize("amount", [COST_ENTRY_AMOUNT_BOUND + 1, -(COST_ENTRY_AMOUNT_BOUND + 1)])
def test_schema_rejects_an_implausible_magnitude(amount: float) -> None:
    with pytest.raises(ValidationError):
        CostEntryIn(project_id=1, category="labour", incurred_on=INCURRED, amount=amount)


@pytest.mark.parametrize("amount", [COST_ENTRY_AMOUNT_BOUND + 1, -(COST_ENTRY_AMOUNT_BOUND + 1)])
def test_db_rejects_an_implausible_magnitude(
    session: Session, project: Project, amount: float
) -> None:
    session.add(CostEntry(project=project, category="labour", incurred_on=INCURRED, amount=amount))
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize("amount", [COST_ENTRY_AMOUNT_BOUND, -COST_ENTRY_AMOUNT_BOUND])
def test_the_bound_itself_is_still_in_range(
    session: Session, project: Project, amount: float
) -> None:
    """The range is inclusive at both ends, schema and DB alike."""
    CostEntryIn(project_id=1, category="labour", incurred_on=INCURRED, amount=amount)
    session.add(CostEntry(project=project, category="labour", incurred_on=INCURRED, amount=amount))
    session.commit()
