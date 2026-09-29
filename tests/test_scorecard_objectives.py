"""Strategic objectives are business-scoped, validated scorecard roots."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)

    def _session() -> Iterator[Session]:
        with new_session_factory(engine)() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_objectives_are_business_scoped_and_protect_their_business(client: TestClient) -> None:
    business = client.post("/businesses", json={"name": "Northstar"})
    assert business.status_code == 201, business.text

    created = client.post(
        "/strategic-objectives",
        json={
            "business_id": business.json()["id"],
            "perspective": "people_capability",
            "name": "Sustain the delivery team",
            "description": "Keep workload inside durable capacity.",
            "owner": "Operations director",
            "active_from": "2026-01-01",
            "active_until": "2026-12-31",
        },
    )

    assert created.status_code == 201, created.text
    objective = created.json()
    assert objective["status"] == "active"
    assert objective["perspective"] == "people_capability"
    assert client.get("/strategic-objectives").json() == [objective]

    protected = client.delete(f"/businesses/{business.json()['id']}")
    assert protected.status_code == 409
    assert "objectives" in protected.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [
        {"business_id": 999, "perspective": "financial", "name": "Orphan"},
        {
            "business_id": 1,
            "perspective": "financial",
            "name": "Inverted window",
            "active_from": "2026-12-31",
            "active_until": "2026-01-01",
        },
    ],
)
def test_objective_refuses_missing_parent_and_inverted_window(
    client: TestClient, body: dict[str, object]
) -> None:
    if body["business_id"] == 1:
        assert client.post("/businesses", json={"name": "Northstar"}).status_code == 201
    refused = client.post("/strategic-objectives", json=body)
    assert refused.status_code == (404 if body["business_id"] == 999 else 422), refused.text
