"""Append-only evidence for objective-owned scorecard metrics."""

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


def test_metric_observations_are_dated_append_only_evidence(client: TestClient) -> None:
    business = client.post("/businesses", json={"name": "Northstar"}).json()["id"]
    objective = client.post(
        "/strategic-objectives",
        json={"business_id": business, "perspective": "financial", "name": "Sustain margin"},
    ).json()["id"]
    definition = client.post(
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
        },
    ).json()["id"]

    recorded = client.post(
        "/metric-observations",
        json={
            "metric_definition_id": definition,
            "observed_on": "2026-08-12",
            "value": 18.5,
            "evidence_note": "Month-end ledger reconciliation.",
        },
    )

    assert recorded.status_code == 201, recorded.text
    observation = recorded.json()
    assert observation["value"] == 18.5
    assert observation["evidence_note"] == "Month-end ledger reconciliation."
    assert (
        client.patch(f"/metric-observations/{observation['id']}", json={"value": 20}).status_code
        == 405
    )
    assert client.delete(f"/metric-observations/{observation['id']}").status_code == 405
    protected = client.delete(f"/metric-definitions/{definition}")
    assert protected.status_code == 409, protected.text
    assert "observations" in protected.json()["detail"]
