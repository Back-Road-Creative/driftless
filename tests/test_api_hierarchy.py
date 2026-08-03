"""Contract tests for the hierarchy CRUD API.

Two carry the design's weight. The mode/unit test covers a rule the database
*cannot* hold: "points for agile, hours for predictive" compares a task to its
project — a different row — so the API is the only upstream gate. The refusal
test proves bad input is rejected before the insert, not surfaced as a 500.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A client bound to a throwaway SQLite file via the session dependency."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)

    def _session() -> Iterator[Session]:
        with new_session_factory(engine)() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create(client: TestClient, path: str, **body: Any) -> int:
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _seed(client: TestClient, mode: str = "agile") -> int:
    """Create the chain down to a workstream and return its id. Portfolio is 1."""
    business = _create(client, "/businesses", name="Back Road Creative")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=business)
    program = _create(client, "/programs", name="Video", portfolio_id=portfolio)
    extra = {"portfolio_id": portfolio, "program_id": program, "delivery_mode": mode}
    project = _create(client, "/projects", name="GoMoveShift 2026", **extra)
    return _create(client, "/workstreams", name="Editing", project_id=project)


def test_create_read_and_list_the_whole_chain(client: TestClient) -> None:
    workstream = _seed(client)
    task = _create(client, "/tasks", name="Cut the trailer", workstream_id=workstream, estimate=5)

    stored = client.get(f"/tasks/{task}").json()
    assert (stored["estimate"], stored["estimate_unit"]) == (5.0, "points")
    assert (stored["status"], stored["percent_complete"]) == ("todo", 0)
    assert [row["name"] for row in client.get("/businesses").json()] == ["Back Road Creative"]
    assert client.get("/projects/1").json()["delivery_mode"] == "agile"
    assert len(client.get("/workstreams").json()) == 1


@pytest.mark.parametrize(
    ("mode", "unit", "status", "detail"),
    [
        ("agile", "points", 201, ""),
        ("agile", "hours", 422, "points"),
        ("predictive", "hours", 201, ""),
        ("predictive", "points", 422, "hours"),
        ("hybrid", "points", 201, ""),
    ],
)
def test_task_unit_must_match_the_projects_delivery_mode(
    client: TestClient, mode: str, unit: str, status: int, detail: str
) -> None:
    body = {"name": "Estimate", "workstream_id": _seed(client, mode), "estimate_unit": unit}
    response = client.post("/tasks", json=body)
    assert response.status_code == status, response.text
    assert detail in response.json().get("detail", "")


def test_a_projects_program_must_live_in_its_own_portfolio(client: TestClient) -> None:
    """A project filed under a foreign portfolio's program would vanish from
    every rollup surface (the grouped walk only yields a portfolio's own
    programs), so the create must refuse the pairing before the row lands."""
    _seed(client)  # business 1, portfolio 1, program 1
    other_business = _create(client, "/businesses", name="Other Business")
    other_portfolio = _create(client, "/portfolios", name="Other", business_id=other_business)
    foreign = _create(client, "/programs", name="Foreign", portfolio_id=other_portfolio)

    strayed = {"name": "Strayed", "portfolio_id": 1, "program_id": foreign}
    refused = client.post("/projects", json=strayed)
    assert refused.status_code == 422, refused.text
    assert "portfolio" in refused.json()["detail"]

    homed = {"name": "Homed", "portfolio_id": other_portfolio, "program_id": foreign}
    assert client.post("/projects", json=homed).status_code == 201, "same-portfolio program is fine"


def test_bad_writes_are_refused_before_they_reach_the_database(client: TestClient) -> None:
    _seed(client)
    orphan = client.post("/portfolios", json={"name": "Orphan", "business_id": 999})
    assert orphan.status_code == 404, "a missing parent must not surface as an FK 500"
    assert orphan.json()["detail"] == "Business 999 not found"
    assert client.get("/projects/999").status_code == 404
    bad_mode = {"name": "Bad mode", "delivery_mode": "waterfall", "portfolio_id": 1}
    assert client.post("/projects", json=bad_mode).status_code == 422
