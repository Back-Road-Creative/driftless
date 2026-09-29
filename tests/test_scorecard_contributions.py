"""Projects explain how they contribute to business strategy."""

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


def test_project_contribution_is_business_scoped_and_named_on_delete(client: TestClient) -> None:
    business = client.post("/businesses", json={"name": "Northstar"}).json()["id"]
    portfolio = client.post(
        "/portfolios", json={"business_id": business, "name": "Delivery"}
    ).json()["id"]
    project = client.post(
        "/projects", json={"portfolio_id": portfolio, "name": "Margin rollout"}
    ).json()["id"]
    objective = client.post(
        "/strategic-objectives",
        json={"business_id": business, "perspective": "financial", "name": "Sustain margin"},
    ).json()["id"]

    created = client.post(
        "/scorecard-contributions",
        json={
            "project_id": project,
            "objective_id": objective,
            "contribution_type": "direct",
            "rationale": "This rollout removes the main margin leak.",
        },
    )

    assert created.status_code == 201, created.text
    assert created.json()["contribution_type"] == "direct"
    updated = client.patch(
        f"/scorecard-contributions/{created.json()['id']}",
        json={"rationale": "The rollout removes the main margin leak."},
    )
    assert updated.status_code == 200, updated.text
    protected_project = client.delete(f"/projects/{project}")
    assert protected_project.status_code == 409, protected_project.text
    assert "scorecard_contributions" in protected_project.json()["detail"]


def test_cross_business_contribution_is_refused(client: TestClient) -> None:
    first = client.post("/businesses", json={"name": "Northstar"}).json()["id"]
    second = client.post("/businesses", json={"name": "Southstar"}).json()["id"]
    portfolio = client.post("/portfolios", json={"business_id": first, "name": "Delivery"}).json()[
        "id"
    ]
    project = client.post("/projects", json={"portfolio_id": portfolio, "name": "Rollout"}).json()[
        "id"
    ]
    objective = client.post(
        "/strategic-objectives",
        json={"business_id": second, "perspective": "financial", "name": "Other margin"},
    ).json()["id"]

    refused = client.post(
        "/scorecard-contributions",
        json={"project_id": project, "objective_id": objective, "contribution_type": "supporting"},
    )
    assert refused.status_code == 409, refused.text


def test_a_contribution_patch_cannot_re_file_it_under_another_objective(
    client: TestClient,
) -> None:
    """``objective_id`` is a parent-scoping FK (``api.schemas._frozen_fk``), so a PATCH
    naming one is a silent no-op rather than a re-file — the same contract every other
    parent-scoping FK holds. ``tests/test_api_write.py`` exercises the cross-business
    guard directly, since no PATCH request can carry this key to reach it."""
    first = client.post("/businesses", json={"name": "Northstar"}).json()["id"]
    second = client.post("/businesses", json={"name": "Southstar"}).json()["id"]
    portfolio = client.post("/portfolios", json={"business_id": first, "name": "Delivery"}).json()[
        "id"
    ]
    project = client.post("/projects", json={"portfolio_id": portfolio, "name": "Rollout"}).json()[
        "id"
    ]
    objective = client.post(
        "/strategic-objectives",
        json={"business_id": first, "perspective": "financial", "name": "Own margin"},
    ).json()["id"]
    other_objective = client.post(
        "/strategic-objectives",
        json={"business_id": second, "perspective": "financial", "name": "Other margin"},
    ).json()["id"]

    created = client.post(
        "/scorecard-contributions",
        json={"project_id": project, "objective_id": objective, "contribution_type": "direct"},
    )
    assert created.status_code == 201, created.text

    moved = client.patch(
        f"/scorecard-contributions/{created.json()['id']}",
        json={"objective_id": other_objective},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["objective_id"] == objective, "a frozen FK moved on a PATCH"
