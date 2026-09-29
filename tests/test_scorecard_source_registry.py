"""Registered scorecard connectors are explicit, business-scoped metadata."""

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


def test_connector_source_must_be_registered_for_the_objectives_business(
    client: TestClient,
) -> None:
    business = client.post("/businesses", json={"name": "Northstar"}).json()["id"]
    objective = client.post(
        "/strategic-objectives",
        json={"business_id": business, "perspective": "financial", "name": "Sustain margin"},
    ).json()["id"]
    missing = client.post(
        "/metric-definitions",
        json={
            "objective_id": objective,
            "name": "Operating margin",
            "direction": "higher_is_better",
            "unit": "percent",
            "target_value": 20,
            "amber_threshold": 15,
            "red_threshold": 10,
            "cadence_days": 30,
            "source_type": "registered_connector",
            "source_key": "finance.ledger",
        },
    )
    assert missing.status_code == 404, missing.text

    registered = client.post(
        "/scorecard-sources",
        json={
            "business_id": business,
            "key": "finance.ledger",
            "name": "Finance ledger",
            "description": "Read-only month-end ledger feed.",
        },
    )
    assert registered.status_code == 201, registered.text
    assert registered.json()["key"] == "finance.ledger"

    created = client.post(
        "/metric-definitions",
        json={
            "objective_id": objective,
            "name": "Operating margin",
            "direction": "higher_is_better",
            "unit": "percent",
            "target_value": 20,
            "amber_threshold": 15,
            "red_threshold": 10,
            "cadence_days": 30,
            "source_type": "registered_connector",
            "source_key": "finance.ledger",
        },
    )
    assert created.status_code == 201, created.text

    retired = client.post(
        "/scorecard-sources",
        json={
            "business_id": business,
            "key": "finance.archive",
            "name": "Retired finance archive",
            "status": "retired",
        },
    )
    assert retired.status_code == 201, retired.text
    refused = client.post(
        "/metric-definitions",
        json={
            "objective_id": objective,
            "name": "Archived margin",
            "direction": "higher_is_better",
            "unit": "percent",
            "target_value": 20,
            "amber_threshold": 15,
            "red_threshold": 10,
            "cadence_days": 30,
            "source_type": "registered_connector",
            "source_key": "finance.archive",
        },
    )
    assert refused.status_code == 409, refused.text


def test_source_keys_are_unique_per_business_and_never_store_credentials(
    client: TestClient,
) -> None:
    business = client.post("/businesses", json={"name": "Northstar"}).json()["id"]
    body = {
        "business_id": business,
        "key": "finance.ledger",
        "name": "Finance ledger",
        "description": "No token or password belongs here.",
    }
    assert client.post("/scorecard-sources", json=body).status_code == 201
    duplicate = client.post("/scorecard-sources", json=body)
    assert duplicate.status_code == 409, duplicate.text
