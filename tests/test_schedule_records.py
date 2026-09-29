"""Contract tests for the schedule records: typed task dependencies, project
calendars and calendar exceptions, estimate scenarios.

The generic create/read/update/delete machinery (``api.crud``) is already
proved by ``tests/test_api_records.py``; these tests exercise this family's
own registration (project scoping, the delete guard, the vocabulary CHECKs)
and its two bespoke cross-row rules: a dependency's cycle refusal and an
estimate scenario's subject-task scoping.
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


def test_a_task_dependency_is_created_and_read_back(client: TestClient) -> None:
    project = _project(client)
    design, build = _task(client, project, "Design"), _task(client, project, "Build")

    dependency = _create(
        client,
        "/task-dependencies",
        predecessor_task_id=design,
        successor_task_id=build,
        kind="FS",
        lag_days=2,
    )

    read = client.get(f"/task-dependencies/{dependency}").json()
    assert read["kind"] == "FS" and read["lag_days"] == 2


def test_an_unknown_dependency_kind_is_refused_by_the_vocabulary(client: TestClient) -> None:
    project = _project(client)
    design, build = _task(client, project, "Design"), _task(client, project, "Build")
    refused = client.post(
        "/task-dependencies",
        json={"predecessor_task_id": design, "successor_task_id": build, "kind": "XX"},
    )
    assert refused.status_code == 422, refused.text


def test_a_task_cannot_depend_on_itself(client: TestClient) -> None:
    project = _project(client)
    design = _task(client, project, "Design")
    refused = client.post(
        "/task-dependencies",
        json={"predecessor_task_id": design, "successor_task_id": design},
    )
    assert refused.status_code == 422, refused.text


def test_a_dependency_crossing_projects_is_refused(client: TestClient) -> None:
    left, right = _project(client, "Left"), _project(client, "Right")
    design, build = _task(client, left, "Design"), _task(client, right, "Build")

    refused = client.post(
        "/task-dependencies",
        json={"predecessor_task_id": design, "successor_task_id": build},
    )
    assert refused.status_code == 422, refused.text


def test_an_edge_that_would_close_a_cycle_is_refused(client: TestClient) -> None:
    project = _project(client)
    design, build, launch = (
        _task(client, project, "Design"),
        _task(client, project, "Build"),
        _task(client, project, "Launch"),
    )
    _create(client, "/task-dependencies", predecessor_task_id=design, successor_task_id=build)
    _create(client, "/task-dependencies", predecessor_task_id=build, successor_task_id=launch)

    refused = client.post(
        "/task-dependencies",
        json={"predecessor_task_id": launch, "successor_task_id": design},
    )

    assert refused.status_code == 409, refused.text
    assert "cycle" in refused.json()["detail"]


def test_a_dependency_deleting_its_predecessor_task_is_refused_by_name(client: TestClient) -> None:
    project = _project(client)
    design, build = _task(client, project, "Design"), _task(client, project, "Build")
    _create(client, "/task-dependencies", predecessor_task_id=design, successor_task_id=build)

    refused = client.delete(f"/tasks/{design}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Task {design} still has dependencies_as_predecessor", (
        "the refusal must name the child, not surface an opaque constraint 409"
    )


def test_a_project_calendar_carries_its_working_days_and_exceptions(client: TestClient) -> None:
    project = _project(client)
    calendar = _create(
        client, "/project-calendars", project_id=project, name="Standard", working_days=31
    )
    exception = _create(
        client,
        "/calendar-exceptions",
        calendar_id=calendar,
        on_date="2026-07-04",
        working=False,
        note="Holiday",
    )

    read = client.get(f"/calendar-exceptions/{exception}").json()
    assert read["working"] is False and read["note"] == "Holiday"

    patched = client.patch(f"/calendar-exceptions/{exception}", json={"working": True})
    assert patched.status_code == 200, patched.text
    assert patched.json()["working"] is True


def test_a_calendar_with_an_exception_is_refused_by_name(client: TestClient) -> None:
    project = _project(client)
    calendar = _create(client, "/project-calendars", project_id=project, name="Standard")
    _create(client, "/calendar-exceptions", calendar_id=calendar, on_date="2026-07-04")

    refused = client.delete(f"/project-calendars/{calendar}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"ProjectCalendar {calendar} still has exceptions", (
        "the refusal must name the child, not surface an opaque constraint 409"
    )


def test_an_estimate_scenario_carries_its_figures_and_provenance(client: TestClient) -> None:
    project = _project(client)
    task = _task(client, project, "Design")
    scenario = _create(
        client,
        "/estimate-scenarios",
        project_id=project,
        target="duration",
        subject_task_id=task,
        kind="three_point",
        inputs='{"optimistic": 3, "likely": 5, "pessimistic": 9}',
        value=5.33,
        low=3.0,
        high=9.0,
        basis="PERT over three estimators",
        actor="Ada Lovelace",
        as_of="2026-01-05",
    )

    read = client.get(f"/estimate-scenarios/{scenario}").json()
    assert read["kind"] == "three_point" and read["value"] == pytest.approx(5.33)
    assert read["subject_task_id"] == task


def test_a_scenario_low_above_its_value_is_refused(client: TestClient) -> None:
    project = _project(client)
    refused = client.post(
        "/estimate-scenarios",
        json={
            "project_id": project,
            "target": "cost",
            "kind": "analogous",
            "value": 100.0,
            "low": 150.0,
            "actor": "Ada Lovelace",
            "as_of": "2026-01-05",
        },
    )
    assert refused.status_code == 409, refused.text


def test_a_scenarios_inputs_must_be_valid_json_text(client: TestClient) -> None:
    project = _project(client)
    refused = client.post(
        "/estimate-scenarios",
        json={
            "project_id": project,
            "target": "cost",
            "kind": "analogous",
            "inputs": "not json",
            "value": 100.0,
            "actor": "Ada Lovelace",
            "as_of": "2026-01-05",
        },
    )
    assert refused.status_code == 422, refused.text


def test_a_scenarios_subject_task_must_belong_to_its_own_project(client: TestClient) -> None:
    home, away = _project(client, "Home"), _project(client, "Away")
    stray_task = _task(client, away, "Stray")

    refused = client.post(
        "/estimate-scenarios",
        json={
            "project_id": home,
            "target": "duration",
            "subject_task_id": stray_task,
            "kind": "analogous",
            "value": 5.0,
            "actor": "Ada Lovelace",
            "as_of": "2026-01-05",
        },
    )
    assert refused.status_code == 409, refused.text


def test_a_project_with_schedule_records_is_refused_by_name(client: TestClient) -> None:
    project = _project(client)
    _create(client, "/project-calendars", project_id=project, name="Standard")

    refused = client.delete(f"/projects/{project}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == f"Project {project} still has calendars", (
        "the refusal must name the child, not surface an opaque constraint 409"
    )


def test_schedule_list_routes_export_csv_symmetrically_with_json(client: TestClient) -> None:
    """The generic ``?format=csv`` registration (``api.crud.reads``) covers this
    family with no bespoke wiring — the same guarantee ``test_api_export.py``
    proves for every list route, exercised here for the ones this change adds."""
    project = _project(client)
    calendar = _create(client, "/project-calendars", project_id=project, name="Standard")
    del calendar

    as_json = client.get("/project-calendars").json()
    as_csv = client.get("/project-calendars", params={"format": "csv"}).text

    assert as_json[0]["name"] == "Standard"
    assert "Standard" in as_csv
    assert as_csv.splitlines()[0] == "project_id,name,working_days,id,row_revision"
