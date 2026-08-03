"""Contract tests for the records / org / narrative / quality / procurement write paths.

The generic create/read/update/delete machinery is exercised once through a
representative spread; the parts with their own logic get their own tests —
StatusSnapshot stamps its percent from calc and never accepts it, SignOff is
append-only, a constraint violation answers 409 not 500, and every write through
the API lands a ChangeLog row so the boundary is auditable.
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api import schemas as s
from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import ChangeLog, register_changelog
from driftless.report import render_document

JAN = "2026-01-31"
MAR = "2026-03-31"


@pytest.fixture
def factory(tmp_path: Path) -> Any:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    made = new_session_factory(engine)
    register_changelog(made)  # the API path is audited; prove it from the test too
    return made


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


def _project_with_evm(client: TestClient) -> int:
    """A predictive project whose single task is 50% done over a 1000-cost line,
    so EV/BAC is exactly 50% at MAR — the figure the snapshot must stamp."""
    project = _project(client)
    workstream = _create(client, "/workstreams", name="Post", project_id=project)
    task = _create(
        client,
        "/tasks",
        name="Grade",
        workstream_id=workstream,
        estimate_unit="hours",
        percent_complete=50,
    )
    baseline = _create(client, "/baselines", project_id=project, version=1)
    _create(
        client,
        "/baseline-lines",
        baseline_id=baseline,
        task_id=task,
        planned_start=JAN,
        planned_finish=MAR,
        planned_cost=1000.0,
    )
    # Approval is one atomic transition, and it comes after the lines are in —
    # the plan of record is frozen the moment it is approved.
    approval = {"status": "approved", "approved_at": f"{JAN}T09:00:00"}
    assert client.patch(f"/baselines/{baseline}", json=approval).status_code == 200
    _create(
        client,
        "/cost-entries",
        project_id=project,
        category="labour",
        incurred_on=JAN,
        amount=400.0,
    )
    return project


@pytest.mark.parametrize(
    ("path", "body", "patch"),
    [
        (
            "/risks",
            {"description": "Batteries slip", "probability": 0.4, "impact": 5000.0},
            {"status": "mitigating"},
        ),
        ("/milestones", {"name": "Cut locked", "target_date": MAR}, {"status": "met"}),
        ("/stakeholders", {"name": "Sponsor"}, {"comms_cadence": "weekly"}),
        (
            "/quality-measurements",
            {"metric": "defects", "target_value": 1.0, "actual_value": 2.0, "measured_on": MAR},
            {"actual_value": 1.0},
        ),
        (
            "/procurement-agreements",
            {"vendor": "DronesRUs", "amount": 1000.0, "start_date": JAN},
            {"status": "active"},
        ),
        (
            "/narrative-artifacts",
            {"kind": "assumption_log", "body": "weather holds"},
            {"body": "weather may not hold"},
        ),
    ],
)
def test_records_crud_round_trip(
    client: TestClient, path: str, body: dict[str, Any], patch: dict[str, Any]
) -> None:
    project = _project(client)
    row_id = _create(client, path, project_id=project, **body)

    assert client.get(f"{path}/{row_id}").status_code == 200
    assert [r["id"] for r in client.get(path).json()] == [row_id]

    patched = client.patch(f"{path}/{row_id}", json=patch)
    assert patched.status_code == 200, patched.text
    key, value = next(iter(patch.items()))
    assert patched.json()[key] == value

    assert client.delete(f"{path}/{row_id}").status_code == 204
    assert client.get(f"{path}/{row_id}").status_code == 404


def test_a_sprint_must_end_strictly_after_it_starts(client: TestClient, factory: Any) -> None:
    """A same-day sprint is DB-legal (the CHECK allows ``>=``) but zero days
    long, which calc refuses — so the boundary refuses it first, on create and
    on patch, and the forecast document keeps rendering instead of dying."""
    business = _create(client, "/businesses", name="Back Road Creative")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=business)
    project = _create(
        client, "/projects", name="GMS", portfolio_id=portfolio, delivery_mode="agile"
    )

    same_day = {"project_id": project, "name": "S0", "start_date": JAN, "end_date": JAN}
    refused = client.post("/sprints", json=same_day)
    assert refused.status_code == 422, refused.text
    assert "start_date" in refused.text

    sprint = _create(
        client,
        "/sprints",
        project_id=project,
        name="S1",
        start_date=JAN,
        end_date=MAR,
        completed_points=10,
    )
    walked = client.patch(f"/sprints/{sprint}", json={"end_date": JAN})
    assert walked.status_code == 422, "a patch must not walk a sprint into zero length"

    with factory() as db:
        stored = db.get(m.Project, project)
        assert stored is not None
        doc = render_document("forecast", db, stored, date(2026, 3, 31))
    assert "10.00" in doc, "the velocity band renders instead of crashing the batch"


def test_legacy_same_day_sprint_row_reads_without_500(client: TestClient, factory: Any) -> None:
    """A same-day sprint predates the round-3 create/patch refusal above and is
    DB-legal (the CHECK allows ``>=``); it can only reach the store by direct
    write, but once there it must still read back. ``SprintOut`` must not inherit
    ``SprintIn``'s ordering rule, or this one legacy row 500s the list for every
    project, not just its own — worse than having no rule at all."""
    business = _create(client, "/businesses", name="Back Road Creative")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=business)
    project = _create(
        client, "/projects", name="GMS", portfolio_id=portfolio, delivery_mode="agile"
    )
    normal = _create(
        client,
        "/sprints",
        project_id=project,
        name="S1",
        start_date=JAN,
        end_date=MAR,
        completed_points=10,
    )

    with factory() as db:
        legacy = m.Sprint(
            project_id=project,
            name="Legacy",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            completed_points=5,
        )
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id

    listed = client.get("/sprints")
    assert listed.status_code == 200, listed.text
    assert {row["id"] for row in listed.json()} == {normal, legacy_id}

    detail = client.get(f"/sprints/{legacy_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["start_date"] == detail.json()["end_date"]


def test_no_out_model_inherits_a_business_validator() -> None:
    """In validates intent, Out serializes truth: a response model must never
    inherit a request-side business validator, or a DB-legal row that predates
    the rule 500s on read instead of deserializing. Sprint is the only request
    model with one today (``schemas._OUT_BASE`` routes its Out twin around it);
    this pins the invariant so a future request that adds a validator and forgets
    to register it fails this test instead of regrowing the same bug."""
    out_names = [name for name in dir(s) if name.endswith("Out")]
    assert out_names  # sanity: something is actually being checked
    for name in out_names:
        model = getattr(s, name)
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            continue
        validators = model.__pydantic_decorators__.model_validators
        assert not validators, f"{name} inherited business validator(s): {list(validators)}"


def test_status_snapshot_stamps_percent_from_calc_and_ignores_the_body(client: TestClient) -> None:
    project = _project_with_evm(client)
    # Even a hand-typed percent in the body is ignored — the schema has no such
    # field, and the endpoint stamps EV/BAC = 50%.
    response = client.post(
        "/status-snapshots",
        json={
            "project_id": project,
            "taken_on": MAR,
            "rag_status": "amber",
            "percent_complete": 99,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["percent_complete"] == 50, "percent is stamped from calc, never accepted"
    assert body["rag_status"] == "amber"


def test_status_snapshot_patch_touches_only_rag_and_note(client: TestClient) -> None:
    project = _project_with_evm(client)
    snap = _create(
        client, "/status-snapshots", project_id=project, taken_on=MAR, rag_status="green"
    )
    patched = client.patch(
        f"/status-snapshots/{snap}", json={"rag_status": "red", "percent_complete": 12}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["rag_status"] == "red"
    assert patched.json()["percent_complete"] == 50, "the stamped percent is not patchable"


def test_sign_off_is_append_only(client: TestClient) -> None:
    project = _project(client)
    first = _create(
        client,
        "/sign-offs",
        project_id=project,
        subject_kind="threat",
        subject_ref="cost:project:1",
        decision="deferred",
        signal=1.4,
        signed_by="jp",
    )
    _create(
        client,
        "/sign-offs",
        project_id=project,
        subject_kind="threat",
        subject_ref="cost:project:1",
        decision="rejected",
        signal=1.4,
        signed_by="jp",
    )
    ledger = client.get("/sign-offs").json()
    assert [s["decision"] for s in ledger] == ["deferred", "rejected"]
    assert ledger[0]["signed_at"] is not None  # server-stamped
    # No mutation surface — the ledger is the whole history.
    assert client.patch(f"/sign-offs/{first}", json={"decision": "accepted"}).status_code == 405
    assert client.delete(f"/sign-offs/{first}").status_code == 405


def test_create_checks_the_parent_exists(client: TestClient) -> None:
    missing = client.post(
        "/risks", json={"project_id": 999, "description": "x", "probability": 0.1, "impact": 1.0}
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Project 999 not found"


def test_boundary_rejects_an_off_vocabulary_value(client: TestClient) -> None:
    project = _project(client)
    bad = client.post(
        "/risks",
        json={
            "project_id": project,
            "description": "x",
            "probability": 0.1,
            "impact": 1.0,
            "status": "worrying",
        },
    )
    assert bad.status_code == 422, "an unknown vocabulary value is a 422, never a CHECK 500"


def test_task_assignee_and_project_department_wire_up(client: TestClient) -> None:
    business = _create(client, "/businesses", name="BRC")
    portfolio = _create(client, "/portfolios", name="Content", business_id=business)
    department = _create(client, "/departments", name="Delivery", business_id=business)
    project = _create(
        client,
        "/projects",
        name="GMS",
        portfolio_id=portfolio,
        delivery_mode="predictive",
        responsible_department_id=department,
    )
    assert client.get(f"/projects/{project}").json()["responsible_department_id"] == department

    person = _create(client, "/people", name="Sam", cost_rate=90.0)
    workstream = _create(client, "/workstreams", name="Post", project_id=project)
    task = _create(
        client,
        "/tasks",
        name="Grade",
        workstream_id=workstream,
        estimate_unit="hours",
        assignee_id=person,
    )
    assert client.get(f"/tasks/{task}").json()["assignee_id"] == person

    orphan = client.post(
        "/tasks",
        json={
            "name": "x",
            "workstream_id": workstream,
            "estimate_unit": "hours",
            "assignee_id": 999,
        },
    )
    assert orphan.status_code == 404 and orphan.json()["detail"] == "Person 999 not found"


def test_constraint_violation_answers_409(client: TestClient) -> None:
    business = _create(client, "/businesses", name="BRC")
    _create(client, "/departments", name="Ops", business_id=business)
    dup = client.post("/departments", json={"name": "Ops", "business_id": business})
    assert dup.status_code == 409, "a unique violation is a conflict, not a 500"


def test_api_writes_are_audited(client: TestClient, factory: Any) -> None:
    _project(client)  # three creates through the API
    with factory() as db:
        logged = db.scalars(select(ChangeLog).where(ChangeLog.operation == "insert")).all()
    tables = {row.table_name for row in logged}
    assert {"business", "portfolio", "project"} <= tables, "every API write lands a ChangeLog row"
