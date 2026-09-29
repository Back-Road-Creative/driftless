"""The procurement calculator page: ``GET /projects/{id}/assist/procurement``."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.models import Business, Portfolio, ProcurementAgreement, Project

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"


def _seed(session: Session) -> None:
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    session.add(
        ProcurementAgreement(project=project, vendor="Acme", status="active", start_date=JAN)
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


def test_the_page_shows_the_agreements_and_the_closure_checklist(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/procurement{Q}").text
    assert "Acme" in body
    assert "0 of 1 agreement closed" in body


def test_the_make_or_buy_what_if_recomputes_without_writing(
    client: TestClient, db: Session
) -> None:
    before = db.query(ProcurementAgreement).count()
    resp = client.get(
        f"/projects/1/assist/procurement{Q}"
        "&make_cost=40&buy_cost=60&volume=3000&fixed_make_cost=50000"
    )
    assert resp.status_code == 200
    body = resp.text
    assert "make" in body
    assert "2500" in body  # break-even
    assert db.query(ProcurementAgreement).count() == before


def test_the_bid_scoring_what_if_recomputes_without_writing(
    client: TestClient, db: Session
) -> None:
    before = db.query(ProcurementAgreement).count()
    resp = client.get(
        f"/projects/1/assist/procurement{Q}"
        "&bidder_a_name=Acme&bidder_a_price=8&bidder_a_quality=6"
        "&bidder_b_name=Bexley&bidder_b_price=6&bidder_b_quality=9"
        "&weight_price=0.6&weight_quality=0.4"
    )
    assert resp.status_code == 200
    body = resp.text
    assert "Bexley" in body
    assert "flips the winner" in body
    assert db.query(ProcurementAgreement).count() == before


def test_the_contract_type_what_if_recomputes_without_writing(
    client: TestClient, db: Session
) -> None:
    before = db.query(ProcurementAgreement).count()
    resp = client.get(
        f"/projects/1/assist/procurement{Q}"
        "&scope_certainty=well_defined&risk_appetite=seller_bears_risk"
    )
    assert resp.status_code == 200
    body = resp.text
    assert "fixed-price" in body
    assert db.query(ProcurementAgreement).count() == before


def test_the_page_carries_its_provenance(client: TestClient) -> None:
    body = client.get(f"/projects/1/assist/procurement{Q}").text
    assert "12.1, 12.2, 12.3" in body
    assert AS_OF.isoformat() in body


def test_an_unknown_project_404s(client: TestClient) -> None:
    assert client.get(f"/projects/999/assist/procurement{Q}").status_code == 404
