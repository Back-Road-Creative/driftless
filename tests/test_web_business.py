"""Unit tests for the business detail surface (/business/{business_id})."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from driftless.models import Business, Portfolio, Program, Project
import test_web_pages

client, db = test_web_pages.client, test_web_pages.db


def test_business_detail_empty_and_populated(client: TestClient, db: Session) -> None:
    business = db.scalars(select(Business)).first()
    if business is None:
        business = Business(name="Acme Corp")
        db.add(business)
        db.commit()

    resp = client.get(f"/business/{business.id}")
    assert resp.status_code == 200
    assert business.name in resp.text

    portfolio = Portfolio(business=business, name="Digital Transformation")
    program = Program(portfolio=portfolio, name="Cloud Migration")
    project = Project(portfolio=portfolio, program=program, name="Migration Core")
    db.add_all([portfolio, program, project])
    db.commit()

    resp2 = client.get(f"/business/{business.id}")
    assert resp2.status_code == 200
    assert "Digital Transformation" in resp2.text
    assert "Cloud Migration" in resp2.text
    assert "Migration Core" in resp2.text
