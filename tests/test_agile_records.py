"""Contract tests for the agile records: roles, backlog items, releases,
definition-of-done items and impediments — plus the fields ``Sprint`` gains
(``goal``, ``release_id``, review/retrospective evidence) so an iteration
carries what it needs without a parallel table.

The generic create/read/update/delete machinery (``api.crud``) is already
proved by ``tests/test_api_records.py``; these tests exercise this family's own
registration (project scoping, the delete guard, the vocabulary CHECKs) and the
one cross-model link — a sprint's ``release``.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.db import Base, new_engine, new_session_factory
from driftless.api.app import app, get_session


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)

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
    return _create(client, "/projects", name="Aurora", portfolio_id=portfolio)


def test_a_project_role_is_created_read_and_patched(client: TestClient) -> None:
    project = _project(client)
    role = _create(
        client, "/project-roles", project_id=project, role="product_owner", holder="Ada Lovelace"
    )

    read = client.get(f"/project-roles/{role}")
    assert read.status_code == 200, read.text
    assert read.json()["holder"] == "Ada Lovelace"

    patched = client.patch(f"/project-roles/{role}", json={"holder": "Grace Hopper"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["holder"] == "Grace Hopper"


def test_an_unknown_role_is_refused_by_the_vocabulary(client: TestClient) -> None:
    project = _project(client)
    refused = client.post(
        "/project-roles", json={"project_id": project, "role": "wizard", "holder": "Merlin"}
    )
    assert refused.status_code == 422, refused.text


def test_a_backlog_item_carries_priority_and_story_points(client: TestClient) -> None:
    project = _project(client)
    item = _create(
        client,
        "/backlog-items",
        project_id=project,
        title="Colour grade the season finale",
        priority="must_have",
        story_points=5,
    )

    read = client.get(f"/backlog-items/{item}").json()
    assert read["priority"] == "must_have"
    assert read["story_points"] == 5
    assert read["status"] == "proposed"  # default


def test_a_negative_story_point_count_is_refused(client: TestClient) -> None:
    project = _project(client)
    refused = client.post(
        "/backlog-items",
        json={"project_id": project, "title": "Impossible", "story_points": -1},
    )
    assert refused.status_code == 422, refused.text


def test_a_release_groups_sprints_and_a_sprint_carries_its_goal(client: TestClient) -> None:
    project = _project(client)
    release = _create(client, "/releases", project_id=project, name="2026 Q1", status="planned")
    sprint = _create(
        client,
        "/sprints",
        project_id=project,
        name="Sprint 1",
        start_date="2026-01-01",
        end_date="2026-01-14",
        goal="Ship the colour-grade pipeline",
        release_id=release,
    )

    read = client.get(f"/sprints/{sprint}").json()
    assert read["goal"] == "Ship the colour-grade pipeline"
    assert read["release_id"] == release
    assert read["review_held_on"] is None
    assert read["retrospective_notes"] is None

    closed = client.patch(
        f"/sprints/{sprint}",
        json={
            "review_held_on": "2026-01-14",
            "review_notes": "Demoed the pipeline end to end.",
            "retrospective_held_on": "2026-01-14",
            "retrospective_notes": "Pairing on the encoder cut rework in half.",
        },
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["review_notes"] == "Demoed the pipeline end to end."
    assert closed.json()["retrospective_notes"] == "Pairing on the encoder cut rework in half."


def test_a_release_with_a_sprint_is_refused_by_name(client: TestClient) -> None:
    project = _project(client)
    release = _create(client, "/releases", project_id=project, name="2026 Q1")
    _create(
        client,
        "/sprints",
        project_id=project,
        name="Sprint 1",
        start_date="2026-01-01",
        end_date="2026-01-14",
        release_id=release,
    )

    refused = client.delete(f"/releases/{release}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Release {release} still has sprints", (
        "the refusal must name the child, not surface an opaque constraint 409"
    )


def test_a_definition_of_done_item_is_a_plain_project_checklist_row(client: TestClient) -> None:
    project = _project(client)
    item = _create(
        client,
        "/definition-of-done-items",
        project_id=project,
        description="Code reviewed and merged to main",
    )

    read = client.get(f"/definition-of-done-items/{item}").json()
    assert read["description"] == "Code reviewed and merged to main"

    deleted = client.delete(f"/definition-of-done-items/{item}")
    assert deleted.status_code == 204, deleted.text


def test_an_impediment_is_dated_like_an_issue(client: TestClient) -> None:
    project = _project(client)
    impediment = _create(
        client,
        "/impediments",
        project_id=project,
        description="Render farm is out of licenses",
        raised_by="Ada Lovelace",
        raised_on="2026-01-05",
    )

    resolved = client.patch(
        f"/impediments/{impediment}",
        json={"status": "resolved", "resolved_on": "2026-01-08"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"


def test_a_project_with_agile_records_is_refused_by_name(client: TestClient) -> None:
    project = _project(client)
    _create(client, "/project-roles", project_id=project, role="scrum_master", holder="Grace")

    refused = client.delete(f"/projects/{project}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Project {project} still has project_roles", (
        "the refusal must name the child, not surface an opaque constraint 409"
    )


def test_agile_list_routes_export_csv_symmetrically_with_json(client: TestClient) -> None:
    """The generic ``?format=csv`` registration (``api.crud.reads``) covers this
    family with no bespoke wiring — the same guarantee ``test_api_export.py``
    proves for every list route, exercised here for the ones this change adds."""
    project = _project(client)
    _create(
        client, "/project-roles", project_id=project, role="developer", holder="Katherine Johnson"
    )

    as_json = client.get("/project-roles").json()
    as_csv = client.get("/project-roles", params={"format": "csv"}).text

    assert as_json[0]["holder"] == "Katherine Johnson"
    assert "Katherine Johnson" in as_csv
    assert as_csv.splitlines()[0] == "project_id,role,holder,id,row_revision"
