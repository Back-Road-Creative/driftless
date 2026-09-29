"""Contract tests for the resource records: resource types and the RBS tree, the
stored RACI, acquisitions, training, team assessments, conflicts and their actions.

The generic create/read/update/delete machinery (``api.crud``) is already proved by
``tests/test_api_records.py``; these tests exercise this family's own registration
(project scoping, the delete guard, the vocabulary CHECKs) and its bespoke cross-row
rules — an RBS node's parent must sit in the same project, an assignment's target
must share its own project, and an assignment names exactly one target.
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


def _project(client: TestClient, name: str = "Aurora") -> int:
    business = _create(client, "/businesses", name=f"BRC {name}")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=business)
    return _create(client, "/projects", name=name, portfolio_id=portfolio)


def _person(client: TestClient, name: str = "Dana") -> int:
    return _create(client, "/people", name=name)


def _task(client: TestClient, project: int, name: str) -> int:
    workstream = _create(client, "/workstreams", name=f"{name} stream", project_id=project)
    return _create(client, "/tasks", name=name, workstream_id=workstream, estimate_unit="hours")


def _deliverable(client: TestClient, project: int, wbs_code: str = "1") -> int:
    return _create(
        client, "/deliverables", project_id=project, name=f"WBS {wbs_code}", wbs_code=wbs_code
    )


def _resource_type(
    client: TestClient, project: int, name: str = "Editor", kind: str = "people"
) -> int:
    return _create(
        client, "/resource-types", project_id=project, name=name, kind=kind, unit="hours", rate=50.0
    )


def test_a_resource_type_is_created_and_read_back(client: TestClient) -> None:
    project = _project(client)
    resource_type = _resource_type(client, project)

    read = client.get(f"/resource-types/{resource_type}").json()
    assert read["kind"] == "people" and read["rate"] == 50.0


def test_an_unknown_resource_type_kind_is_refused_by_the_vocabulary(client: TestClient) -> None:
    project = _project(client)
    refused = client.post(
        "/resource-types",
        json={"project_id": project, "name": "Editor", "kind": "bogus"},
    )
    assert refused.status_code == 422, refused.text


def test_a_resource_breakdown_node_is_created_and_read_back(client: TestClient) -> None:
    project = _project(client)
    resource_type = _resource_type(client, project)

    node = _create(
        client,
        "/resource-breakdowns",
        project_id=project,
        resource_type_id=resource_type,
        quantity=2.0,
    )

    read = client.get(f"/resource-breakdowns/{node}").json()
    assert read["quantity"] == 2.0 and read["parent_id"] is None


def test_a_resource_breakdown_node_can_nest_under_a_parent_in_its_own_project(
    client: TestClient,
) -> None:
    project = _project(client)
    resource_type = _resource_type(client, project)
    parent = _create(
        client, "/resource-breakdowns", project_id=project, resource_type_id=resource_type
    )

    child = _create(
        client,
        "/resource-breakdowns",
        project_id=project,
        resource_type_id=resource_type,
        parent_id=parent,
    )

    read = client.get(f"/resource-breakdowns/{child}").json()
    assert read["parent_id"] == parent


def test_a_resource_breakdown_parent_must_belong_to_its_own_project(client: TestClient) -> None:
    home, away = _project(client, "Home"), _project(client, "Away")
    away_type = _resource_type(client, away)
    stray_parent = _create(
        client, "/resource-breakdowns", project_id=away, resource_type_id=away_type
    )
    home_type = _resource_type(client, home, name="Rig")

    refused = client.post(
        "/resource-breakdowns",
        json={"project_id": home, "resource_type_id": home_type, "parent_id": stray_parent},
    )
    assert refused.status_code == 409, refused.text


def test_an_assignment_is_filed_against_a_deliverable(client: TestClient) -> None:
    project = _project(client)
    deliverable = _deliverable(client, project)
    person = _person(client)

    assignment = _create(
        client,
        "/responsibility-assignments",
        project_id=project,
        deliverable_id=deliverable,
        person_id=person,
        role="accountable",
    )

    read = client.get(f"/responsibility-assignments/{assignment}").json()
    assert read["deliverable_id"] == deliverable and read["role"] == "accountable"
    assert read["task_id"] is None


def test_an_assignment_naming_zero_targets_is_refused(client: TestClient) -> None:
    project = _project(client)
    person = _person(client)

    refused = client.post(
        "/responsibility-assignments", json={"project_id": project, "person_id": person}
    )
    assert refused.status_code == 422, refused.text


def test_an_assignment_naming_two_targets_is_refused(client: TestClient) -> None:
    project = _project(client)
    deliverable = _deliverable(client, project)
    task = _task(client, project, "Build")
    person = _person(client)

    refused = client.post(
        "/responsibility-assignments",
        json={
            "project_id": project,
            "deliverable_id": deliverable,
            "task_id": task,
            "person_id": person,
        },
    )
    assert refused.status_code == 422, refused.text


def test_an_assignment_crossing_projects_is_refused(client: TestClient) -> None:
    left, right = _project(client, "Left"), _project(client, "Right")
    stray_task = _task(client, right, "Build")
    person = _person(client)

    refused = client.post(
        "/responsibility-assignments",
        json={"project_id": left, "task_id": stray_task, "person_id": person},
    )
    assert refused.status_code == 422, refused.text


def test_an_acquisition_is_created_and_read_back(client: TestClient) -> None:
    project = _project(client)
    resource_type = _resource_type(client, project, name="Steadicam", kind="equipment")

    acquisition = _create(
        client,
        "/acquisitions",
        project_id=project,
        resource_type_id=resource_type,
        source="external",
        requested_on="2026-01-01",
        status="fulfilled",
        fulfilled_on="2026-01-05",
    )

    read = client.get(f"/acquisitions/{acquisition}").json()
    assert read["status"] == "fulfilled" and read["fulfilled_on"] == "2026-01-05"


def test_an_acquisition_fulfilled_before_requested_is_refused(client: TestClient) -> None:
    project = _project(client)
    resource_type = _resource_type(client, project)

    refused = client.post(
        "/acquisitions",
        json={
            "project_id": project,
            "resource_type_id": resource_type,
            "requested_on": "2026-01-10",
            "fulfilled_on": "2026-01-01",
        },
    )
    assert refused.status_code == 409, refused.text


def test_a_training_record_is_created_and_read_back(client: TestClient) -> None:
    person = _person(client)

    record = _create(
        client, "/training-records", person_id=person, topic="Safety", completed_on="2026-02-01"
    )

    read = client.get(f"/training-records/{record}").json()
    assert read["topic"] == "Safety"


def test_a_team_assessment_is_appended_and_read_back(client: TestClient) -> None:
    project = _project(client)

    assessment = _create(
        client,
        "/team-assessments",
        project_id=project,
        assessed_on="2026-03-01",
        dimension="Performing",
        score=80.0,
        actor="pm",
    )

    read = client.get(f"/team-assessments/{assessment}").json()
    assert read["score"] == 80.0


def test_a_team_assessment_score_out_of_range_is_refused(client: TestClient) -> None:
    project = _project(client)

    refused = client.post(
        "/team-assessments",
        json={
            "project_id": project,
            "assessed_on": "2026-03-01",
            "dimension": "Performing",
            "score": 150.0,
            "actor": "pm",
        },
    )
    assert refused.status_code == 422, refused.text


def test_a_team_assessment_has_no_patch_or_delete(client: TestClient) -> None:
    project = _project(client)
    assessment = _create(
        client,
        "/team-assessments",
        project_id=project,
        assessed_on="2026-03-01",
        dimension="Performing",
        score=80.0,
        actor="pm",
    )

    assert client.patch(f"/team-assessments/{assessment}", json={}).status_code == 405
    assert client.delete(f"/team-assessments/{assessment}").status_code == 405


def test_a_conflict_is_filed_and_read_back(client: TestClient) -> None:
    project = _project(client)

    conflict = _create(
        client,
        "/conflict-records",
        project_id=project,
        raised_on="2026-04-01",
        parties="Editor, Sound mixer",
        approach="compromise",
        actor="pm",
    )

    read = client.get(f"/conflict-records/{conflict}").json()
    assert read["approach"] == "compromise" and read["resolved_on"] is None


def test_a_conflict_resolved_before_raised_is_refused(client: TestClient) -> None:
    project = _project(client)

    refused = client.post(
        "/conflict-records",
        json={
            "project_id": project,
            "raised_on": "2026-04-10",
            "parties": "A, B",
            "resolved_on": "2026-04-01",
            "actor": "pm",
        },
    )
    assert refused.status_code == 409, refused.text


def test_a_conflict_action_is_filed_against_a_conflict(client: TestClient) -> None:
    project = _project(client)
    conflict = _create(
        client,
        "/conflict-records",
        project_id=project,
        raised_on="2026-04-01",
        parties="A, B",
        actor="pm",
    )
    owner = _person(client)

    action = _create(
        client, "/conflict-actions", conflict_id=conflict, owner_id=owner, due_on="2026-04-08"
    )

    read = client.get(f"/conflict-actions/{action}").json()
    assert read["due_on"] == "2026-04-08" and read["done_on"] is None


def test_a_conflict_with_an_action_is_refused_by_name(client: TestClient) -> None:
    project = _project(client)
    conflict = _create(
        client,
        "/conflict-records",
        project_id=project,
        raised_on="2026-04-01",
        parties="A, B",
        actor="pm",
    )
    owner = _person(client)
    _create(client, "/conflict-actions", conflict_id=conflict, owner_id=owner)

    refused = client.delete(f"/conflict-records/{conflict}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"ConflictRecord {conflict} still has actions"


def test_a_project_with_resource_records_is_refused_by_name(client: TestClient) -> None:
    project = _project(client)
    _resource_type(client, project)

    refused = client.delete(f"/projects/{project}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Project {project} still has resource_types"


def test_resource_list_routes_export_csv_symmetrically_with_json(client: TestClient) -> None:
    """The generic ``?format=csv`` registration (``api.crud.reads``) covers this
    family with no bespoke wiring — the same guarantee ``test_api_export.py``
    proves for every list route, exercised here for the ones this change adds."""
    project = _project(client)
    _resource_type(client, project, name="Editor")

    as_json = client.get("/resource-types").json()
    as_csv = client.get("/resource-types", params={"format": "csv"}).text

    assert as_json[0]["name"] == "Editor"
    assert "Editor" in as_csv
