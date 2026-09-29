"""Contract tests for the department operations records: services, the work
queue, recurring work, service levels, operating controls, incidents,
improvements — plus the department half of ``BudgetLine``'s scope.

The generic create/read/update/delete machinery (``api.crud``) is already
proved by ``tests/test_api_records.py``; these tests exercise this family's
own registration (department scoping, the delete guard, the vocabulary
CHECKs) and the cross-model links — a work request's/service level's
``service_id`` and an incident's ``control_id``.
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


def _department(client: TestClient) -> int:
    business = _create(client, "/businesses", name="Back Road Creative")
    return _create(client, "/departments", name="Post Production", business_id=business)


def test_a_department_service_is_created_read_and_patched(client: TestClient) -> None:
    dept = _department(client)
    service = _create(
        client,
        "/department-services",
        department_id=dept,
        name="Colour grading",
        owner="Ada Lovelace",
    )

    read = client.get(f"/department-services/{service}")
    assert read.status_code == 200, read.text
    assert read.json()["owner"] == "Ada Lovelace"

    patched = client.patch(f"/department-services/{service}", json={"owner": "Grace Hopper"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["owner"] == "Grace Hopper"


def test_a_work_request_carries_the_work_item_shaped_dates(client: TestClient) -> None:
    dept = _department(client)
    service = _create(
        client, "/department-services", department_id=dept, name="Colour grading", owner="Ada"
    )
    request = _create(
        client,
        "/work-requests",
        department_id=dept,
        service_id=service,
        requester="Grace Hopper",
        raised_on="2026-01-05",
        priority="high",
    )

    read = client.get(f"/work-requests/{request}").json()
    assert read["status"] == "requested"  # default
    assert read["priority"] == "high"

    started = client.patch(f"/work-requests/{request}", json={"started_on": "2026-01-06"})
    assert started.status_code == 200, started.text

    too_early = client.patch(f"/work-requests/{request}", json={"done_on": "2026-01-04"})
    assert too_early.status_code in (409, 422), too_early.text


def test_a_work_request_service_must_belong_to_the_same_department(client: TestClient) -> None:
    dept = _department(client)
    other_business = _create(client, "/businesses", name="Other Co")
    other_dept = _create(client, "/departments", name="Ops", business_id=other_business)
    foreign_service = _create(
        client, "/department-services", department_id=other_dept, name="Ops desk", owner="Sam"
    )

    refused = client.post(
        "/work-requests",
        json={
            "department_id": dept,
            "service_id": foreign_service,
            "requester": "Grace Hopper",
            "raised_on": "2026-01-05",
        },
    )
    assert refused.status_code == 409, refused.text


def test_an_unknown_priority_is_refused_by_the_vocabulary(client: TestClient) -> None:
    dept = _department(client)
    refused = client.post(
        "/work-requests",
        json={
            "department_id": dept,
            "requester": "Grace Hopper",
            "raised_on": "2026-01-05",
            "priority": "whenever",
        },
    )
    assert refused.status_code == 422, refused.text


def test_recurring_work_carries_a_cadence_and_next_due_date(client: TestClient) -> None:
    dept = _department(client)
    item = _create(
        client,
        "/recurring-work",
        department_id=dept,
        name="Weekly render-farm audit",
        cadence="weekly",
        owner="Sam",
        next_due_on="2026-02-01",
    )

    read = client.get(f"/recurring-work/{item}").json()
    assert read["cadence"] == "weekly"
    assert read["next_due_on"] == "2026-02-01"


def test_a_service_level_targets_a_department_service(client: TestClient) -> None:
    dept = _department(client)
    service = _create(
        client, "/department-services", department_id=dept, name="Colour grading", owner="Ada"
    )
    level = _create(
        client,
        "/service-levels",
        department_id=dept,
        service_id=service,
        measure="turnaround_hours",
        target=48,
        window="weekly",
    )

    read = client.get(f"/service-levels/{level}").json()
    assert read["target"] == 48
    assert read["window"] == "weekly"


def test_an_operating_control_with_an_incident_is_refused_by_name(client: TestClient) -> None:
    dept = _department(client)
    control = _create(
        client,
        "/operating-controls",
        department_id=dept,
        name="Dual approval on vendor payments",
        owner="Sam",
    )
    _create(
        client,
        "/incidents",
        department_id=dept,
        control_id=control,
        description="A payment cleared without the second signature",
        raised_on="2026-01-05",
    )

    refused = client.delete(f"/operating-controls/{control}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"OperatingControl {control} still has incidents", (
        "the refusal must name the child, not surface an opaque constraint 409"
    )


def test_an_incident_control_must_belong_to_the_same_department(client: TestClient) -> None:
    dept = _department(client)
    other_business = _create(client, "/businesses", name="Other Co")
    other_dept = _create(client, "/departments", name="Ops", business_id=other_business)
    foreign_control = _create(
        client, "/operating-controls", department_id=other_dept, name="Ops control", owner="Sam"
    )

    refused = client.post(
        "/incidents",
        json={
            "department_id": dept,
            "control_id": foreign_control,
            "description": "Something went wrong",
            "raised_on": "2026-01-05",
        },
    )
    assert refused.status_code == 409, refused.text


def test_an_incident_resolved_before_it_was_raised_is_refused(client: TestClient) -> None:
    dept = _department(client)
    refused = client.post(
        "/incidents",
        json={
            "department_id": dept,
            "description": "A late render",
            "raised_on": "2026-01-05",
            "resolved_on": "2026-01-01",
        },
    )
    assert refused.status_code in (409, 422), refused.text


def test_an_improvement_carries_what_why_owner_and_status(client: TestClient) -> None:
    dept = _department(client)
    improvement = _create(
        client,
        "/improvements",
        department_id=dept,
        what="Automate the render-farm license check",
        why="Manual checks missed a licence expiry twice this quarter",
        owner="Sam",
    )

    read = client.get(f"/improvements/{improvement}").json()
    assert read["status"] == "proposed"  # default

    closed = client.patch(f"/improvements/{improvement}", json={"status": "done"})
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "done"


def test_a_budget_line_scopes_to_a_department_instead_of_a_project(client: TestClient) -> None:
    dept = _department(client)
    line = _create(
        client,
        "/budget-lines",
        department_id=dept,
        category="services",
        planned_amount=5000,
    )

    read = client.get(f"/budget-lines/{line}").json()
    assert read["department_id"] == dept
    assert read["project_id"] is None


def test_a_budget_line_needs_exactly_one_scope(client: TestClient) -> None:
    business = _create(client, "/businesses", name="Back Road Creative")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=business)
    project = _create(client, "/projects", name="Aurora", portfolio_id=portfolio)
    dept = _create(client, "/departments", name="Post Production", business_id=business)

    neither = client.post("/budget-lines", json={"category": "services", "planned_amount": 100})
    assert neither.status_code == 422, neither.text

    both = client.post(
        "/budget-lines",
        json={
            "project_id": project,
            "department_id": dept,
            "category": "services",
            "planned_amount": 100,
        },
    )
    assert both.status_code == 422, both.text


def test_a_department_with_operations_records_is_refused_by_name(client: TestClient) -> None:
    dept = _department(client)
    _create(client, "/department-services", department_id=dept, name="Colour grading", owner="Ada")

    business = _create(client, "/businesses", name="Elsewhere")
    refused = client.patch(f"/departments/{dept}", json={"business_id": business})

    assert refused.status_code == 409, refused.text
    assert "department_services" in refused.json()["detail"], (
        "the refusal must name the child holding the department in place"
    )


def test_operations_list_routes_export_csv_symmetrically_with_json(client: TestClient) -> None:
    """The generic ``?format=csv`` registration (``api.crud.reads``) covers this
    family with no bespoke wiring — the same guarantee ``test_api_export.py``
    proves for every list route, exercised here for the ones this change adds."""
    dept = _department(client)
    _create(
        client,
        "/operating-controls",
        department_id=dept,
        name="Dual approval on vendor payments",
        owner="Sam",
    )

    as_json = client.get("/operating-controls").json()
    as_csv = client.get("/operating-controls", params={"format": "csv"}).text

    assert as_json[0]["owner"] == "Sam"
    assert "Sam" in as_csv
    assert as_csv.splitlines()[0] == "department_id,name,description,owner,id,row_revision"
