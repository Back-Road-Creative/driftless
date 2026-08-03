"""The narrative vocabulary carries the fifteen prose artifact kinds beyond the legacy four.

The new stored kinds deliberately EQUAL their catalog artifact kinds (unlike the four
legacy short names), which is what let each resolver wave be one mapping entry per kind:
the ten management plans came first, and the scope statement, requirements documentation,
team charter, basis of estimates and team performance assessments complete the set. So
storage no longer runs ahead of tracking — every kind the API accepts a body for resolves
against the store, and a written body is what "present" means for all fifteen.
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.pmbok import mapping
from driftless.pmbok.artifacts import ARTIFACT_KINDS

#: The pre-existing short-name kinds; everything beyond them must speak catalog.
_LEGACY = ("assumption_log", "eef", "opa", "lessons_learned")

_AS_OF = date(2026, 3, 31)


@pytest.fixture
def factory(tmp_path: Path) -> Any:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    return new_session_factory(engine)


@pytest.fixture
def client(factory: Any) -> Iterator[TestClient]:
    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create(client: TestClient, path: str, **body: Any) -> int:
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _project(client: TestClient) -> int:
    business = _create(client, "/businesses", name="Back Road Creative")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=business)
    return _create(
        client, "/projects", name="GMS", portfolio_id=portfolio, delivery_mode="predictive"
    )


def test_every_new_stored_kind_is_its_catalog_artifact_kind() -> None:
    new_kinds = tuple(k for k in m.NARRATIVE_KINDS if k not in _LEGACY)
    assert len(new_kinds) == 15, (
        f"expected the fifteen prose kinds beyond the legacy four, found {len(new_kinds)}"
    )
    off_catalog = [k for k in new_kinds if k not in ARTIFACT_KINDS]
    assert not off_catalog, f"stored kind must equal its catalog artifact kind: {off_catalog}"


def test_a_stored_management_plan_round_trips_and_resolves_present(
    client: TestClient, factory: Any
) -> None:
    """The resolver wave: a plan body stored through the API is what its resolver reads."""
    project_id = _project(client)
    created = client.post(
        "/narrative-artifacts",
        json={
            "project_id": project_id,
            "kind": "risk_management_plan",
            "body": "Risks are reviewed fortnightly; exposure over 10k escalates to the PMO.",
        },
    )
    assert created.status_code == 201, created.text
    fetched = client.get(f"/narrative-artifacts/{created.json()['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["kind"] == "risk_management_plan"

    assert mapping.is_tracked("risk_management_plan")
    with factory() as db:
        project = db.get(m.Project, project_id)
        assert project is not None
        assert mapping.resolve("risk_management_plan", project, db, _AS_OF).present is True


def test_the_stored_prose_vocabulary_and_its_resolvers_have_converged(
    client: TestClient, factory: Any
) -> None:
    """Storable no longer runs ahead of tracked: every stored prose kind resolves.

    A team charter body lands through the API and its resolver reads it present, while
    the estimating basis nobody wrote reads absent rather than ``not tracked`` — the
    boundary the earlier waves left open is closed, so the store cannot accept a body
    for a kind it would then report it does not track.
    """
    unresolved = [k for k in m.NARRATIVE_KINDS if k not in _LEGACY and not mapping.is_tracked(k)]
    assert not unresolved, f"the API stores prose for kinds with no resolver: {unresolved}"
    assert mapping.is_tracked("basis_of_estimates")

    project_id = _project(client)
    created = client.post(
        "/narrative-artifacts",
        json={
            "project_id": project_id,
            "kind": "team_charter",
            "body": "Core hours 10-3; decisions by the pair on call; retro every second Friday.",
        },
    )
    assert created.status_code == 201, created.text

    with factory() as db:
        project = db.get(m.Project, project_id)
        assert project is not None
        assert mapping.resolve("team_charter", project, db, _AS_OF).present is True
        unwritten = mapping.resolve("basis_of_estimates", project, db, _AS_OF)
    assert unwritten.present is False and unwritten.detail != "not tracked"
