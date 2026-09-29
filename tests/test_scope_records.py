"""Contract tests for the scope records: requirements, requirement traces, the
WBS/deliverable tree and the acceptance ledger.

The generic create/read/update/delete machinery (``api.crud``) is already proved by
``tests/test_api_records.py``; these tests exercise this family's own registration
(project scoping, the delete guard, the vocabulary CHECKs) and its bespoke cross-row
rules — a trace's requirement and its one target must share a project, a deliverable's
parent must sit in the same project, and a trace names exactly one target.
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


def _task(client: TestClient, project: int, name: str) -> int:
    workstream = _create(client, "/workstreams", name=f"{name} stream", project_id=project)
    return _create(client, "/tasks", name=name, workstream_id=workstream, estimate_unit="hours")


def _requirement(client: TestClient, project: int, code: str = "REQ-1") -> int:
    return _create(
        client,
        "/requirements",
        project_id=project,
        code=code,
        statement="Must ship on time",
        actor="pm",
    )


def _deliverable(client: TestClient, project: int, wbs_code: str = "1.1", **extra: Any) -> int:
    return _create(
        client,
        "/deliverables",
        project_id=project,
        name=f"WBS {wbs_code}",
        wbs_code=wbs_code,
        **extra,
    )


def test_a_requirement_is_created_and_read_back(client: TestClient) -> None:
    project = _project(client)
    requirement = _requirement(client, project)

    read = client.get(f"/requirements/{requirement}").json()
    assert read["code"] == "REQ-1" and read["status"] == "proposed"


def test_an_unknown_requirement_category_is_refused_by_the_vocabulary(client: TestClient) -> None:
    project = _project(client)
    refused = client.post(
        "/requirements",
        json={
            "project_id": project,
            "code": "REQ-1",
            "statement": "x",
            "category": "bogus",
            "actor": "pm",
        },
    )
    assert refused.status_code == 422, refused.text


def test_a_requirements_source_stakeholder_must_belong_to_its_own_project(
    client: TestClient,
) -> None:
    home, away = _project(client, "Home"), _project(client, "Away")
    stray = _create(client, "/stakeholders", project_id=away, name="Stray")

    refused = client.post(
        "/requirements",
        json={
            "project_id": home,
            "code": "REQ-1",
            "statement": "x",
            "source_stakeholder_id": stray,
            "actor": "pm",
        },
    )
    assert refused.status_code == 409, refused.text


def test_a_deliverable_is_created_and_read_back(client: TestClient) -> None:
    project = _project(client)
    deliverable = _deliverable(client, project)

    read = client.get(f"/deliverables/{deliverable}").json()
    assert read["wbs_code"] == "1.1" and read["status"] == "planned"


def test_a_deliverable_parent_must_belong_to_its_own_project(client: TestClient) -> None:
    home, away = _project(client, "Home"), _project(client, "Away")
    stray_parent = _deliverable(client, away, "1")

    refused = client.post(
        "/deliverables",
        json={
            "project_id": home,
            "name": "Child",
            "wbs_code": "1.1",
            "parent_id": stray_parent,
        },
    )
    assert refused.status_code == 409, refused.text


def test_a_trace_is_filed_against_a_deliverable(client: TestClient) -> None:
    project = _project(client)
    requirement = _requirement(client, project)
    deliverable = _deliverable(client, project)

    trace = _create(
        client, "/requirement-traces", requirement_id=requirement, deliverable_id=deliverable
    )

    read = client.get(f"/requirement-traces/{trace}").json()
    assert read["deliverable_id"] == deliverable
    assert read["task_id"] is None and read["backlog_item_id"] is None


def test_a_trace_naming_zero_targets_is_refused(client: TestClient) -> None:
    project = _project(client)
    requirement = _requirement(client, project)

    refused = client.post("/requirement-traces", json={"requirement_id": requirement})
    assert refused.status_code == 422, refused.text


def test_a_trace_naming_two_targets_is_refused(client: TestClient) -> None:
    project = _project(client)
    requirement = _requirement(client, project)
    deliverable = _deliverable(client, project)
    task = _task(client, project, "Build")

    refused = client.post(
        "/requirement-traces",
        json={"requirement_id": requirement, "deliverable_id": deliverable, "task_id": task},
    )
    assert refused.status_code == 422, refused.text


def test_a_trace_crossing_projects_is_refused(client: TestClient) -> None:
    left, right = _project(client, "Left"), _project(client, "Right")
    requirement = _requirement(client, left)
    stray_task = _task(client, right, "Build")

    refused = client.post(
        "/requirement-traces",
        json={"requirement_id": requirement, "task_id": stray_task},
    )
    assert refused.status_code == 422, refused.text


def test_an_acceptance_record_is_appended_and_read_back(client: TestClient) -> None:
    project = _project(client)
    deliverable = _deliverable(client, project)

    record = _create(
        client,
        "/acceptance-records",
        deliverable_id=deliverable,
        verified_on="2026-01-01",
        accepted_on="2026-01-05",
        actor="pm",
        note="Passed inspection",
    )

    read = client.get(f"/acceptance-records/{record}").json()
    assert read["verified_on"] == "2026-01-01" and read["accepted_on"] == "2026-01-05"


def test_an_acceptance_record_with_no_date_is_refused(client: TestClient) -> None:
    project = _project(client)
    deliverable = _deliverable(client, project)

    refused = client.post(
        "/acceptance-records", json={"deliverable_id": deliverable, "actor": "pm"}
    )
    assert refused.status_code == 422, refused.text


def test_an_acceptance_record_has_no_patch_or_delete(client: TestClient) -> None:
    project = _project(client)
    deliverable = _deliverable(client, project)
    record = _create(
        client,
        "/acceptance-records",
        deliverable_id=deliverable,
        verified_on="2026-01-01",
        actor="pm",
    )

    assert client.patch(f"/acceptance-records/{record}", json={}).status_code == 405
    assert client.delete(f"/acceptance-records/{record}").status_code == 405


def test_a_deliverable_with_a_trace_is_refused_by_name(client: TestClient) -> None:
    project = _project(client)
    requirement = _requirement(client, project)
    deliverable = _deliverable(client, project)
    _create(client, "/requirement-traces", requirement_id=requirement, deliverable_id=deliverable)

    refused = client.delete(f"/deliverables/{deliverable}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Deliverable {deliverable} still has traces_as_target", (
        "the refusal must name the child, not surface an opaque constraint 409"
    )


def test_a_deliverable_with_an_acceptance_record_is_refused_by_name(client: TestClient) -> None:
    project = _project(client)
    deliverable = _deliverable(client, project)
    _create(
        client,
        "/acceptance-records",
        deliverable_id=deliverable,
        verified_on="2026-01-01",
        actor="pm",
    )

    refused = client.delete(f"/deliverables/{deliverable}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Deliverable {deliverable} still has acceptance_records"


def test_a_deliverable_with_children_is_refused_by_name(client: TestClient) -> None:
    project = _project(client)
    parent = _deliverable(client, project, "1")
    _deliverable(client, project, "1.1", parent_id=parent)

    refused = client.delete(f"/deliverables/{parent}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Deliverable {parent} still has children"


def test_a_requirement_with_a_trace_is_refused_by_name(client: TestClient) -> None:
    project = _project(client)
    requirement = _requirement(client, project)
    deliverable = _deliverable(client, project)
    _create(client, "/requirement-traces", requirement_id=requirement, deliverable_id=deliverable)

    refused = client.delete(f"/requirements/{requirement}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Requirement {requirement} still has traces"


def test_a_project_with_scope_records_is_refused_by_name(client: TestClient) -> None:
    project = _project(client)
    _requirement(client, project)

    refused = client.delete(f"/projects/{project}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Project {project} still has requirements"


def test_scope_list_routes_export_csv_symmetrically_with_json(client: TestClient) -> None:
    """The generic ``?format=csv`` registration (``api.crud.reads``) covers this
    family with no bespoke wiring — the same guarantee ``test_api_export.py``
    proves for every list route, exercised here for the ones this change adds."""
    project = _project(client)
    _requirement(client, project)

    as_json = client.get("/requirements").json()
    as_csv = client.get("/requirements", params={"format": "csv"}).text

    assert as_json[0]["code"] == "REQ-1"
    assert "REQ-1" in as_csv
