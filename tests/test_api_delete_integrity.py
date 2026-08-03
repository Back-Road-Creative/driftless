"""Contract tests for deleting a project that owns delivery records.

This pins an interaction that neither of the two files involved states on its
own, so it is easy to undo by accident from either side:

* ``driftless.api.app._delete`` reads the blocking child sets off the *mapper* —
  every relationship whose direction is ONETOMANY, with no exclusion for
  ``viewonly`` ones.
* ``Project.baselines``, ``Project.milestones`` and ``Project.sprints`` in
  ``driftless.models.hierarchy`` are declared ``viewonly=True``, because the
  writable side of each of those foreign keys is the child's own ``project``.

Together they mean a project carrying a baseline, a milestone or a sprint
cannot be deleted, even though none of those collections can be written through
from the project side. That is the behaviour we want — dropping a project with
an approved plan under it would destroy the numbers a report was built from —
but it is emergent, so it is asserted here rather than assumed. Each of the
three is checked individually: removing one relationship, or filtering
``viewonly`` out of the guard, must fail loudly right here.

Delivery records have no API routes, so they are written straight to the
database through a second session on the same engine. The engine is a file, not
``sqlite://`` — an in-memory URL gives every connection its own empty database
and the API's session would find no tables at all.
"""

from collections.abc import Callable, Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Baseline, Milestone, Sprint

START, FINISH = date(2026, 1, 1), date(2026, 1, 10)

# One record per viewonly relationship on ``Project``, keyed by the relationship
# name the guard puts in its 409 detail.
BUILD: dict[str, Callable[[int], Baseline | Milestone | Sprint]] = {
    "baselines": lambda project_id: Baseline(
        project_id=project_id,
        version=1,
        status="approved",
        approved_at=datetime(2026, 1, 1, 9, 0),
    ),
    "milestones": lambda project_id: Milestone(
        project_id=project_id, name="Season one live", target_date=FINISH
    ),
    "sprints": lambda project_id: Sprint(
        project_id=project_id, name="Sprint 1", start_date=START, end_date=FINISH
    ),
}
MODEL: dict[str, type[Base]] = {
    "baselines": Baseline,
    "milestones": Milestone,
    "sprints": Sprint,
}


@pytest.fixture
def bound(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    """A client and a session factory sharing one throwaway SQLite file."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as test_client:
        yield test_client, factory
    app.dependency_overrides.clear()


def _create(client: TestClient, path: str, **body: Any) -> int:
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _seed_project(client: TestClient) -> int:
    """A project with no children of any kind — the clean-delete starting point."""
    business = _create(client, "/businesses", name="Back Road Creative")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=business)
    return _create(client, "/projects", name="GoMoveShift 2026", portfolio_id=portfolio)


def _attach(factory: sessionmaker[Session], project_id: int, relationship: str) -> int:
    """Write one delivery record for the project and return its id."""
    with factory() as db:
        row = BUILD[relationship](project_id)
        db.add(row)
        db.commit()
        return int(row.id)


def _remove(factory: sessionmaker[Session], relationship: str, row_id: int) -> None:
    with factory() as db:
        stored = db.get(MODEL[relationship], row_id)
        assert stored is not None
        db.delete(stored)
        db.commit()


def test_a_project_with_no_delivery_records_deletes(
    bound: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = bound
    project = _seed_project(client)

    assert client.delete(f"/projects/{project}").status_code == 204
    assert client.get(f"/projects/{project}").status_code == 404


@pytest.mark.parametrize("relationship", list(BUILD))
def test_a_project_owning_a_delivery_record_is_refused(
    bound: tuple[TestClient, sessionmaker[Session]], relationship: str
) -> None:
    client, factory = bound
    project = _seed_project(client)
    _attach(factory, project, relationship)

    refused = client.delete(f"/projects/{project}")
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Project {project} still has {relationship}", (
        "the refusal must name what blocks it, so an operator knows what to clear"
    )
    assert client.get(f"/projects/{project}").status_code == 200, "a refusal changes nothing"


def test_a_project_owning_a_record_child_is_refused_by_name(
    bound: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """The guard reads blocking children off the mapper, so a record child that
    declares no parent-side collection on ``Project`` used to fall through to an
    opaque IntegrityError 409 ("constraint violation"). With the collection
    declared, the refusal names what blocks it — "still has risks" — so an
    operator knows what to clear."""
    client, _ = bound
    project = _seed_project(client)
    _create(
        client,
        "/risks",
        project_id=project,
        description="Lead editor turnover mid-season",
        probability=0.5,
        impact=1000.0,
    )

    refused = client.delete(f"/projects/{project}")
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Project {project} still has risks", (
        "the refusal must name the record child, not surface an opaque constraint 409"
    )


@pytest.mark.parametrize("relationship", list(BUILD))
def test_clearing_the_record_releases_the_project(
    bound: tuple[TestClient, sessionmaker[Session]], relationship: str
) -> None:
    """The refusal tracks live children — it is not a permanent lock on the row."""
    client, factory = bound
    project = _seed_project(client)
    row_id = _attach(factory, project, relationship)
    assert client.delete(f"/projects/{project}").status_code == 409

    _remove(factory, relationship, row_id)

    assert client.delete(f"/projects/{project}").status_code == 204
    assert client.get(f"/projects/{project}").status_code == 404
