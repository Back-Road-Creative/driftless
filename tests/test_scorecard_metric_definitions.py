"""Contract for objective-owned scorecard metric definitions."""

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


def test_metric_definition_owns_directional_thresholds_and_a_trusted_source(
    client: TestClient,
) -> None:
    business = client.post("/businesses", json={"name": "Northstar"}).json()["id"]
    objective = client.post(
        "/strategic-objectives",
        json={"business_id": business, "perspective": "financial", "name": "Sustain margin"},
    ).json()["id"]

    body = {
        "objective_id": objective,
        "name": "Operating margin",
        "direction": "higher_is_better",
        "unit": "percent",
        "target_value": 20,
        "amber_threshold": 15,
        "red_threshold": 10,
        "cadence_days": 30,
        "source_type": "manual",
    }
    created = client.post("/metric-definitions", json=body)

    assert created.status_code == 201, created.text
    assert created.json()["source_type"] == "manual"
    protected = client.delete(f"/strategic-objectives/{objective}")
    assert protected.status_code == 409, protected.text
    assert "metric_definitions" in protected.json()["detail"]
    assert (
        client.post(
            "/metric-definitions",
            json={
                "objective_id": objective,
                "name": "Broken thresholds",
                "direction": "higher_is_better",
                "unit": "percent",
                "target_value": 20,
                "amber_threshold": 10,
                "red_threshold": 15,
                "cadence_days": 30,
                "source_type": "manual",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/metric-definitions",
            json={
                "objective_id": objective,
                "name": "Manual with a connector key",
                "direction": "higher_is_better",
                "unit": "percent",
                "target_value": 20,
                "amber_threshold": 15,
                "red_threshold": 10,
                "cadence_days": 30,
                "source_type": "manual",
                "source_key": "not-allowed",
            },
        ).status_code
        == 422
    )

    # Versioned, not mutable (docs/temporal-model.md): a PATCH cannot move the
    # identity or any grading input in place -- correcting one is a new dated
    # row, never an edit. REFUSED rather than quietly dropped: a caller who reads
    # 200 over a discarded threshold goes on trusting a number nothing changed.
    original = created.json()
    attempt = client.patch(
        f"/metric-definitions/{original['id']}", json={"target_value": 90, "owner": "Finance"}
    )
    assert attempt.status_code == 422, attempt.text
    assert "target_value" in attempt.text
    # Whole-row equality, so an unbumped ``row_revision`` is part of the pin: a
    # refusal that moved it would tell an If-Match client the write had landed.
    assert client.get(f"/metric-definitions/{original['id']}").json() == original

    # A field no report grades on is still an ordinary in-place edit.
    ordinary = client.patch(f"/metric-definitions/{original['id']}", json={"owner": "Finance"})
    assert ordinary.status_code == 200 and ordinary.json()["owner"] == "Finance", ordinary.text

    # One objective still cannot carry the same metric name twice: undated rows
    # share one sentinel date so the widened constraint still sees them collide.
    duplicate = client.post("/metric-definitions", json=body)
    assert duplicate.status_code == 409, duplicate.text
    dated = client.post("/metric-definitions", json={**body, "effective_from": "2026-09-01"})
    assert dated.status_code == 201, "a DATED supersession is the supported way to change one"
