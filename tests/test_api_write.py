"""Contract tests for the deferred write half of the API: update and delete.

Three carry the design's weight. Partial update must leave an omitted field
alone — the whole point of ``exclude_unset``, and the bug a naive ``model_dump``
would ship. The mode/unit pairing must hold on *update* too, or a task can be
walked into an invalid state the create gate would have refused. And delete
must refuse to orphan children, because a hierarchy whose parents can vanish
underneath their rollups is worse than no hierarchy at all.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import Response
from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session, sessionmaker

from driftless import models
from driftless.api import schemas as s
from driftless.api.app import app, get_session
from driftless.api.rules import contribution_patch_stays_in_business, line_still_open_and_inside
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Baseline


@pytest.fixture
def bound(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    """A client and a session factory over one throwaway SQLite file.

    The factory is for rows the API itself refuses to write — a legacy row, or
    one some future path produced — which is the only way to test a guard that
    exists precisely because such a row must not be trusted.
    """
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


@pytest.fixture
def client(bound: tuple[TestClient, sessionmaker[Session]]) -> TestClient:
    """A client bound to a throwaway SQLite file via the session dependency."""
    return bound[0]


def _create(client: TestClient, path: str, **body: Any) -> int:
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _seed(client: TestClient, mode: str = "agile", tag: str = "a") -> int:
    """Create a business -> portfolio -> project -> workstream chain; return the workstream."""
    business = _create(client, "/businesses", name=f"Back Road Creative {tag}")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=business)
    project = _create(client, "/projects", name="GMS", portfolio_id=portfolio, delivery_mode=mode)
    return _create(client, "/workstreams", name="Editing", project_id=project)


def _sibling_projects(client: TestClient) -> tuple[int, int]:
    """Two projects in two businesses — ours, and one we must never write into."""
    ours = client.get(f"/workstreams/{_seed(client, tag='ours')}").json()["project_id"]
    theirs = client.get(f"/workstreams/{_seed(client, tag='theirs')}").json()["project_id"]
    return int(ours), int(theirs)


def _risk(client: TestClient, project: int) -> int:
    body = {"description": "Editor churn", "probability": 0.5, "impact": 1.0}
    return _create(client, "/risks", project_id=project, **body)


_ISSUE = {"description": "The lead editor left", "raised_on": "2026-01-05"}
_CHANGE = {"description": "Add a fourth episode", "raised_on": "2026-01-05", "status": "approved"}
_RESPONSE = {
    "strategy": "mitigate",
    "trigger": "Vendor outage exceeds one day",
    "planned_action": "Fail over to the secondary vendor",
    "residual_probability": 0.1,
    "residual_impact": 200.0,
    "cost_of_response": 500.0,
    "schedule_days": 3,
    "status": "planned",
    "actor": "pm",
    "as_of": "2026-02-20",
}


def test_omitting_a_field_leaves_it_unchanged(client: TestClient) -> None:
    workstream = _seed(client)
    task = _create(client, "/tasks", name="Cut the trailer", workstream_id=workstream, estimate=5)

    patched = client.patch(f"/tasks/{task}", json={"status": "in_progress"})
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["status"] == "in_progress"
    assert body["name"] == "Cut the trailer", "an omitted field must not be blanked"
    assert (body["estimate"], body["estimate_unit"]) == (5.0, "points")
    assert client.get(f"/tasks/{task}").json() == body


def test_an_explicit_null_is_not_an_omission(client: TestClient) -> None:
    task = _create(client, "/tasks", name="Grade", workstream_id=_seed(client), estimate=8)

    cleared = client.patch(f"/tasks/{task}", json={"estimate": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["estimate"] is None, "an explicit null must clear a nullable field"
    assert client.patch(f"/tasks/{task}", json={"name": None}).status_code == 422


def test_a_task_carries_actual_and_forecast_finish_through_create_patch_and_get(
    client: TestClient,
) -> None:
    workstream = _seed(client)
    response = client.post(
        "/tasks",
        json={
            "name": "Cut",
            "workstream_id": workstream,
            "actual_finish": "2026-06-15",
            "forecast_finish": "2026-06-20",
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["actual_finish"] == "2026-06-15"
    assert created["forecast_finish"] == "2026-06-20"
    assert "row_revision" in created

    task = created["id"]
    fetched = client.get(f"/tasks/{task}").json()
    assert fetched["actual_finish"] == "2026-06-15"
    assert fetched["forecast_finish"] == "2026-06-20"

    patched = client.patch(f"/tasks/{task}", json={"forecast_finish": "2026-07-01"})
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["forecast_finish"] == "2026-07-01"
    assert body["actual_finish"] == "2026-06-15", "an omitted field must not be blanked"
    assert client.get(f"/tasks/{task}").json() == body


@pytest.mark.parametrize(
    ("mode", "unit", "new_unit", "status", "detail"),
    [
        ("agile", "points", "hours", 422, "points"),
        ("predictive", "hours", "points", 422, "hours"),
        ("hybrid", "points", "hours", 200, ""),
    ],
)
def test_task_unit_must_match_the_projects_delivery_mode_on_update(
    client: TestClient, mode: str, unit: str, new_unit: str, status: int, detail: str
) -> None:
    workstream = _seed(client, mode)
    task = _create(client, "/tasks", name="Estimate", workstream_id=workstream, estimate_unit=unit)
    response = client.patch(f"/tasks/{task}", json={"estimate_unit": new_unit})
    assert response.status_code == status, response.text
    assert detail in response.json().get("detail", "")


def test_a_task_cannot_change_workstream_across_projects(client: TestClient) -> None:
    """A task moves between its own project's workstreams, never out of it: a
    workstream in another project would reopen the baseline-line cross-project
    hole from the task side. The move is refused outright, naming both projects,
    rather than answered 200 with the field quietly dropped — a client must be
    able to tell a refusal from a move that landed."""
    agile = _seed(client, "agile", "agile")
    predictive = _seed(client, "predictive", "predictive")
    task = _create(client, "/tasks", name="Port", workstream_id=agile, estimate_unit="points")

    moved = client.patch(f"/tasks/{task}", json={"workstream_id": predictive})
    assert moved.status_code == 409, moved.text
    assert "belongs to project" in moved.json()["detail"]
    assert client.get(f"/tasks/{task}").json()["workstream_id"] == agile, (
        "the task cannot follow a patch into another project's workstream"
    )
    # The unit rule still governs the fields that DO patch, in the task's own mode.
    assert client.patch(f"/tasks/{task}", json={"estimate_unit": "hours"}).status_code == 422


def test_a_task_moves_between_its_own_projects_workstreams(client: TestClient) -> None:
    """Refiling a task under a sibling workstream keeps it inside the same
    project's rollup, so it is the correction a misfiled task actually has. The
    row must move: a 200 whose response still reports the old workstream is
    indistinguishable from an ignored request."""
    editing = _seed(client, "agile")
    project = client.get(f"/workstreams/{editing}").json()["project_id"]
    grading = _create(client, "/workstreams", name="Grading", project_id=project)
    task = _create(client, "/tasks", name="Cut", workstream_id=editing, estimate_unit="points")

    moved = client.patch(f"/tasks/{task}", json={"workstream_id": grading})
    assert moved.status_code == 200, moved.text
    assert moved.json()["workstream_id"] == grading
    assert client.get(f"/tasks/{task}").json()["workstream_id"] == grading, "the move must land"

    paired = {"workstream_id": editing, "estimate_unit": "hours"}
    assert client.patch(f"/tasks/{task}", json=paired).status_code == 422, (
        "the mode/unit rule still reads the task as the move would leave it"
    )
    assert client.get(f"/tasks/{task}").json()["workstream_id"] == grading, (
        "a refusal moves nothing"
    )


def test_a_task_under_an_approved_baseline_can_still_be_refiled(client: TestClient) -> None:
    """The dead end an inert ``workstream_id`` left behind: an approved baseline
    freezes its lines and the delete guard refuses a task that still has one, so a
    task misfiled under the wrong workstream had no correction route at all — not
    the patch, not delete+recreate. Moving it inside its own project touches
    neither the frozen plan nor any rollup."""
    editing = _seed(client)
    project = client.get(f"/workstreams/{editing}").json()["project_id"]
    grading = _create(client, "/workstreams", name="Grading", project_id=project)
    task = _create(client, "/tasks", name="Cut", workstream_id=editing)
    baseline = _create(client, "/baselines", project_id=project, version=1)
    line = _create(client, "/baseline-lines", **_line(baseline, task))
    approval = {"status": "approved", "approved_at": "2026-01-01T09:00:00"}
    assert client.patch(f"/baselines/{baseline}", json=approval).status_code == 200

    assert client.delete(f"/baseline-lines/{line}").status_code == 409, (
        "the plan of record is frozen"
    )
    assert client.delete(f"/tasks/{task}").status_code == 409, "and the task still has that line"
    moved = client.patch(f"/tasks/{task}", json={"workstream_id": grading})
    assert moved.status_code == 200, moved.text
    assert client.get(f"/tasks/{task}").json()["workstream_id"] == grading


def test_a_projects_program_must_stay_in_its_portfolio_on_update(client: TestClient) -> None:
    """Both patch directions are refused: pointing ``program_id`` at a foreign
    program, and moving ``portfolio_id`` away from the program's home. Either
    would strand the project outside every rollup the grouped walk builds."""
    business = _create(client, "/businesses", name="Back Road Creative")
    home = _create(client, "/portfolios", name="Home", business_id=business)
    away = _create(client, "/portfolios", name="Away", business_id=business)
    home_program = _create(client, "/programs", name="Video", portfolio_id=home)
    away_program = _create(client, "/programs", name="Audio", portfolio_id=away)
    project = _create(client, "/projects", name="GMS", portfolio_id=home, program_id=home_program)

    strayed = client.patch(f"/projects/{project}", json={"program_id": away_program})
    assert strayed.status_code == 422, "a program from another portfolio must be refused"
    assert "portfolio" in strayed.json()["detail"]
    moved = client.patch(f"/projects/{project}", json={"portfolio_id": away})
    assert moved.status_code == 422, "leaving the program's home portfolio must be refused"

    both = {"portfolio_id": away, "program_id": away_program}
    assert client.patch(f"/projects/{project}", json=both).status_code == 200, (
        "the rule reads the row as the patch will leave it — moving both together is fine"
    )


def test_moving_a_program_with_projects_out_of_its_portfolio_is_refused(
    client: TestClient,
) -> None:
    """A schema-valid PATCH must not strand projects under a program their
    portfolio does not own — the grouped rollup walk fails loudly on exactly
    that row, taking the dashboard down until the move is reverted."""
    business = _create(client, "/businesses", name="Back Road Creative")
    home = _create(client, "/portfolios", name="Home", business_id=business)
    away = _create(client, "/portfolios", name="Away", business_id=business)
    program = _create(client, "/programs", name="Video", portfolio_id=home)
    project = _create(client, "/projects", name="GMS", portfolio_id=home, program_id=program)

    moved = client.patch(f"/programs/{program}", json={"portfolio_id": away})
    assert moved.status_code == 409, "moving a program out from under its projects must refuse"
    detail = moved.json()["detail"]
    assert "1 project" in detail and str(project) in detail
    assert client.get("/").status_code == 200, "the dashboard must keep rendering"

    childless = _create(client, "/programs", name="Childless", portfolio_id=home)
    assert client.patch(f"/programs/{childless}", json={"portfolio_id": away}).status_code == 200


def test_update_checks_a_new_parent_exists(client: TestClient) -> None:
    _seed(client)
    moved = client.patch("/portfolios/1", json={"business_id": 999})
    assert moved.status_code == 404, "a missing parent must not surface as an FK 500"
    assert moved.json()["detail"] == "Business 999 not found"


def test_delete_refuses_to_orphan_children(client: TestClient) -> None:
    workstream = _seed(client)
    task = _create(client, "/tasks", name="Cut", workstream_id=workstream)

    refused = client.delete("/businesses/1")
    assert refused.status_code == 409, refused.text
    assert "portfolios" in refused.json()["detail"]
    assert client.delete(f"/workstreams/{workstream}").status_code == 409
    assert client.get(f"/workstreams/{workstream}").status_code == 200, "a refusal changes nothing"

    assert client.delete(f"/tasks/{task}").status_code == 204
    assert client.delete(f"/workstreams/{workstream}").status_code == 204
    assert client.get(f"/workstreams/{workstream}").status_code == 404


def test_updating_or_deleting_a_missing_row_is_404(client: TestClient) -> None:
    assert client.patch("/programs/999", json={"name": "Ghost"}).status_code == 404
    assert client.delete("/programs/999").status_code == 404
    assert client.delete("/tasks/999").json()["detail"] == "Task 999 not found"


def _line(baseline: int, task: int) -> dict[str, Any]:
    return {
        "baseline_id": baseline,
        "task_id": task,
        "planned_start": "2026-01-01",
        "planned_finish": "2026-03-31",
        "planned_cost": 100.0,
    }


def test_flipping_a_projects_mode_under_mismatched_tasks_is_refused(client: TestClient) -> None:
    """A mode flip that landed would write-lock every mismatched task: the row
    itself violates the unit rule, so each later patch 422s until the flip is
    reverted. The flip is refused instead, and the tasks stay editable."""
    workstream = _seed(client, "agile")
    project = client.get(f"/workstreams/{workstream}").json()["project_id"]
    task = _create(client, "/tasks", name="Cut", workstream_id=workstream, estimate_unit="points")

    flipped = client.patch(f"/projects/{project}", json={"delivery_mode": "predictive"})
    assert flipped.status_code == 409, "a mode flip must not strand existing tasks"
    detail = flipped.json()["detail"]
    assert "1 task" in detail and str(task) in detail
    assert client.patch(f"/tasks/{task}", json={"status": "done"}).status_code == 200, (
        "the refusal is exactly what keeps the task row patchable"
    )
    hybrid = client.patch(f"/projects/{project}", json={"delivery_mode": "hybrid"})
    assert hybrid.status_code == 200, "hybrid takes either unit, so that flip stays open"


def test_moving_a_workstream_into_a_mismatched_mode_is_refused(client: TestClient) -> None:
    workstream = _seed(client, "agile", "agile")
    home = client.get(f"/workstreams/{_seed(client, 'predictive', 'p')}").json()["project_id"]
    task = _create(client, "/tasks", name="Port", workstream_id=workstream, estimate_unit="points")

    moved = client.patch(f"/workstreams/{workstream}", json={"project_id": home})
    assert moved.status_code == 409, "points tasks cannot follow their workstream into predictive"
    assert str(task) in moved.json()["detail"]
    assert client.delete(f"/tasks/{task}").status_code == 204
    emptied = client.patch(f"/workstreams/{workstream}", json={"project_id": home})
    assert emptied.status_code == 200, "an empty workstream moves freely — the rule tracks tasks"


def test_a_workstream_carrying_tasks_cannot_change_project(client: TestClient) -> None:
    """A workstream move is a batched task move, and the task side already refuses
    that across projects. Left open, one 200 relocated every task under the
    workstream without touching a task row — walking them out from under an
    approved baseline's lines without passing the plan freeze, so a frozen line in
    project A ended up planning work that now lives in project B."""
    editing = _seed(client, "agile", "ours")
    home = client.get(f"/workstreams/{editing}").json()["project_id"]
    away = client.get(f"/workstreams/{_seed(client, 'agile', 'theirs')}").json()["project_id"]
    task = _create(client, "/tasks", name="Cut", workstream_id=editing)
    baseline = _create(client, "/baselines", project_id=home, version=1)
    _create(client, "/baseline-lines", **_line(baseline, task))
    approval = {"status": "approved", "approved_at": "2026-01-01T09:00:00"}
    assert client.patch(f"/baselines/{baseline}", json=approval).status_code == 200

    moved = client.patch(f"/workstreams/{editing}", json={"project_id": away})
    assert moved.status_code == 409, moved.text
    assert f"({task})" in moved.json()["detail"], "the refusal names the tasks that hold it"
    assert client.get(f"/workstreams/{editing}").json()["project_id"] == home, (
        "an approved plan's line must not end up planning another project's work"
    )

    assert client.patch(f"/workstreams/{editing}", json={"project_id": home}).status_code == 200, (
        "a project_id that changes nothing is not a move"
    )
    empty = _create(client, "/workstreams", name="Grading", project_id=home)
    assert client.patch(f"/workstreams/{empty}", json={"project_id": away}).status_code == 200, (
        "emptied of tasks the move is legitimate and still goes through"
    )


def test_a_secondary_link_may_only_point_inside_its_own_project(client: TestClient) -> None:
    """``Issue.risk_id`` and ``ChangeRequest.resulting_baseline_id`` are links
    rather than parents, so the patch twin keeps them — and neither write path
    scoped either one. A foreign link corrupts every reader that takes it as
    same-project: the register reads a risk's issues as its own lineage, the scope
    report reads a change request's baseline as the version it produced, and the
    delete guard lets one project's risk be held undeletable from another's. The
    same link inside the row's own project is the legitimate case and still lands."""
    ours, theirs = _sibling_projects(client)
    plans = [_create(client, "/baselines", project_id=p, version=1) for p in (theirs, ours)]
    for path, body, field, (foreign, own) in (
        ("/issues", _ISSUE, "risk_id", (_risk(client, theirs), _risk(client, ours))),
        ("/change-requests", _CHANGE, "resulting_baseline_id", tuple(plans)),
    ):
        borrowed = client.post(path, json={**body, "project_id": ours, field: foreign})
        assert borrowed.status_code == 409, borrowed.text
        assert "belongs to project" in borrowed.json()["detail"]

        row = _create(client, path, project_id=ours, **body)
        strayed = client.patch(f"{path}/{row}", json={field: foreign})
        assert strayed.status_code == 409, "nor may a patch point it across projects"
        assert client.get(f"{path}/{row}").json()[field] is None, "a refusal changes nothing"

        linked = client.patch(f"{path}/{row}", json={field: own})
        assert linked.status_code == 200, linked.text
        assert linked.json()[field] == own, "the same link in its own project still lands"


def test_a_baseline_line_may_only_plan_its_own_projects_task(client: TestClient) -> None:
    """One project's EV must not borrow another's task — a foreign line lets
    project A report earned value from work only project B owns."""
    ours = _seed(client, "agile", "ours")
    theirs = _seed(client, "agile", "theirs")
    project = client.get(f"/workstreams/{ours}").json()["project_id"]
    foreign = _create(client, "/tasks", name="Theirs", workstream_id=theirs)
    baseline = _create(client, "/baselines", project_id=project, version=1)

    borrowed = client.post("/baseline-lines", json=_line(baseline, foreign))
    assert borrowed.status_code == 422, borrowed.text
    assert "belongs to project" in borrowed.json()["detail"]

    task = _create(client, "/tasks", name="Ours", workstream_id=ours)
    line = _create(client, "/baseline-lines", **_line(baseline, task))
    strayed = client.patch(
        f"/baseline-lines/{line}", json={"task_id": foreign, "planned_cost": 7.0}
    )
    assert strayed.status_code == 200, strayed.text
    landed = client.get(f"/baseline-lines/{line}").json()
    assert landed["task_id"] == task, "a line's task is frozen — it cannot point across projects"
    assert landed["planned_cost"] == 7.0, "a non-parent field still updates"


def test_an_approved_baseline_and_its_lines_are_frozen(client: TestClient) -> None:
    """Approval makes the baseline the plan of record: the approval patch is the
    last write it takes. Edits, line edits, line deletes and late lines are all
    refused — a plan change is a new version."""
    workstream = _seed(client)
    project = client.get(f"/workstreams/{workstream}").json()["project_id"]
    task = _create(client, "/tasks", name="Cut", workstream_id=workstream)
    baseline = _create(client, "/baselines", project_id=project, version=1)
    line = _create(client, "/baseline-lines", **_line(baseline, task))

    approval = {"status": "approved", "approved_at": "2026-01-01T09:00:00"}
    assert client.patch(f"/baselines/{baseline}", json=approval).status_code == 200, (
        "approval itself is the one transition an unapproved baseline accepts"
    )

    assert client.patch(f"/baselines/{baseline}", json={"version": 3}).status_code == 409
    assert client.patch(f"/baseline-lines/{line}", json={"planned_cost": 1.0}).status_code == 409
    assert client.delete(f"/baseline-lines/{line}").status_code == 409
    second = _create(client, "/tasks", name="Grade", workstream_id=workstream)
    late = client.post("/baseline-lines", json=_line(baseline, second))
    assert late.status_code == 409, "a late line rewrites the approved plan too"

    draft = _create(client, "/baselines", project_id=project, version=2)
    parked = _create(client, "/baseline-lines", **_line(draft, second))
    slid = client.patch(f"/baseline-lines/{parked}", json={"baseline_id": baseline})
    assert slid.status_code == 200, slid.text
    assert client.get(f"/baseline-lines/{parked}").json()["baseline_id"] == draft, (
        "a line's baseline is frozen — it cannot slide into the approved plan"
    )
    assert client.get(f"/baseline-lines/{line}").json()["planned_cost"] == 100.0, (
        "a refusal changes nothing"
    )


def test_a_line_patch_naming_a_different_approved_baseline_refuses(
    bound: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """Defence in depth for the slide the patch twin already makes inert.

    ``BaselineLinePatch`` drops ``baseline_id`` by construction, so no HTTP
    request reaches the destination check inside ``line_still_open_and_inside``
    today — the test above proves the attempt is inert. The check is what stops
    a future twin, or a future write path that passes ``baseline_id`` through,
    sliding a draft's line into an approved plan; deleting it would ship
    silently. Called here exactly as the patch path calls it: an approved
    destination refuses 409, and a still-open sibling passes, proving the
    refusal is about approval rather than about moving at all."""
    client, factory = bound
    workstream = _seed(client)
    project = client.get(f"/workstreams/{workstream}").json()["project_id"]
    task = _create(client, "/tasks", name="Cut", workstream_id=workstream)
    draft = _create(client, "/baselines", project_id=project, version=1)
    line = _create(client, "/baseline-lines", **_line(draft, task))
    approved = _create(client, "/baselines", project_id=project, version=2)
    approval = {"status": "approved", "approved_at": "2026-01-01T09:00:00"}
    assert client.patch(f"/baselines/{approved}", json=approval).status_code == 200
    sibling = _create(client, "/baselines", project_id=project, version=3)

    with factory() as db:
        row = db.get(models.BaselineLine, line)
        assert row is not None
        with pytest.raises(HTTPException) as caught:
            line_still_open_and_inside(db, row, {"baseline_id": approved})
        assert caught.value.status_code == 409
        assert f"Baseline {approved} is approved" in caught.value.detail
        line_still_open_and_inside(db, row, {"baseline_id": sibling})  # an open target passes


def test_a_contribution_patch_naming_a_cross_business_objective_refuses(
    bound: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """The same defence-in-depth as the baseline-line check above:
    ``ScorecardContributionPatch`` drops ``project_id``/``objective_id`` by
    construction, so no HTTP request reaches this check with either key today —
    the create-time twin (``contribution_stays_in_business``) already proves the
    boundary at the moment a contribution is filed. This is what stops a future
    patch twin, or a future write path that passes either key through, from
    quietly re-filing a contribution under an objective owned by a different
    business than the project it names."""
    client, factory = bound
    business = _create(client, "/businesses", name="Northstar")
    other_business = _create(client, "/businesses", name="Southstar")
    portfolio = _create(client, "/portfolios", name="Delivery", business_id=business)
    project = _create(client, "/projects", name="Rollout", portfolio_id=portfolio)
    objective = _create(
        client, "/strategic-objectives", business_id=business, perspective="financial", name="Own"
    )
    other_objective = _create(
        client,
        "/strategic-objectives",
        business_id=other_business,
        perspective="financial",
        name="Other",
    )
    contribution = _create(
        client,
        "/scorecard-contributions",
        project_id=project,
        objective_id=objective,
        contribution_type="direct",
    )

    with factory() as db:
        row = db.get(models.ScorecardContribution, contribution)
        assert row is not None
        with pytest.raises(HTTPException) as caught:
            contribution_patch_stays_in_business(db, row, {"objective_id": other_objective})
        assert caught.value.status_code == 409
        assert "belong to different businesses" in caught.value.detail
        # the same objective passes -- the refusal is about the businesses disagreeing
        contribution_patch_stays_in_business(db, row, {"objective_id": objective})


def test_a_child_record_cannot_be_reparented_across_projects(client: TestClient) -> None:
    """The whole class of cross-project reparent holes: a partial update that
    moved ``project_id`` would silently lift a row out of one project's rollup and
    drop it into another's — a $999999 budget line, or a missed milestone injected
    into a foreign rollup. The FK is absent from the patch twin, so the attempt is
    inert: the row stays home while non-parent fields still update."""
    here = _seed(client, tag="here")
    there = _seed(client, tag="there")
    here_project = client.get(f"/workstreams/{here}").json()["project_id"]
    there_project = client.get(f"/workstreams/{there}").json()["project_id"]

    budget_line = _create(
        client,
        "/budget-lines",
        project_id=here_project,
        category="labour",
        planned_amount=999999.0,
    )
    moved = client.patch(
        f"/budget-lines/{budget_line}", json={"project_id": there_project, "planned_amount": 5.0}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["project_id"] == here_project, "the budget line cannot leave its project"
    assert moved.json()["planned_amount"] == 5.0, "a non-parent field still updates"

    milestone = _create(
        client, "/milestones", project_id=here_project, name="Launch", target_date="2026-03-31"
    )
    client.patch(f"/milestones/{milestone}", json={"project_id": there_project})
    assert client.get(f"/milestones/{milestone}").json()["project_id"] == here_project, (
        "a milestone cannot be injected into another project's rollup"
    )


def test_moving_a_populated_portfolio_to_another_business_is_refused(client: TestClient) -> None:
    """A portfolio move carries every program, project and record under it into
    another business in one call, silently rewriting both businesses' rollups.
    Emptied, the move is still a legitimate operation."""
    home = _create(client, "/businesses", name="Back Road Creative")
    away = _create(client, "/businesses", name="Other Co")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=home)
    program = _create(client, "/programs", name="Video", portfolio_id=portfolio)

    moved = client.patch(f"/portfolios/{portfolio}", json={"business_id": away})
    assert moved.status_code == 409, "a populated portfolio must not change business"
    assert "programs" in moved.json()["detail"]
    assert client.get(f"/portfolios/{portfolio}").json()["business_id"] == home

    assert client.delete(f"/programs/{program}").status_code == 204
    assert client.patch(f"/portfolios/{portfolio}", json={"business_id": away}).status_code == 200


def test_moving_a_staffed_department_to_another_business_is_refused(client: TestClient) -> None:
    """A department's people and the projects it is accountable for belong to its
    business; moving the department alone files them under a business that does
    not employ them."""
    home = _create(client, "/businesses", name="Back Road Creative")
    away = _create(client, "/businesses", name="Other Co")
    department = _create(client, "/departments", name="Post", business_id=home)
    person = _create(client, "/people", name="JP", department_id=department)

    staffed = client.patch(f"/departments/{department}", json={"business_id": away})
    assert staffed.status_code == 409, "a staffed department must not change business"
    assert "people" in staffed.json()["detail"]
    assert client.delete(f"/people/{person}").status_code == 204

    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=home)
    _create(
        client,
        "/projects",
        name="GMS",
        portfolio_id=portfolio,
        responsible_department_id=department,
    )
    accountable = client.patch(f"/departments/{department}", json={"business_id": away})
    assert accountable.status_code == 409, "nor may one accountable for a project"
    assert "responsible projects" in accountable.json()["detail"]


def test_a_programless_project_cannot_be_moved_across_businesses(client: TestClient) -> None:
    """``require_program_in_portfolio`` returns early when ``program_id`` is None,
    and a program is optional by design — so the common programless project could
    be re-filed under any portfolio in any business, taking its cost entries and
    every record under it out of the business that owns the work."""
    home = _create(client, "/businesses", name="Back Road Creative")
    away = _create(client, "/businesses", name="Other Co")
    ours = _create(client, "/portfolios", name="Content Brands", business_id=home)
    sibling = _create(client, "/portfolios", name="Client Work", business_id=home)
    theirs = _create(client, "/portfolios", name="Theirs", business_id=away)
    project = _create(client, "/projects", name="GMS", portfolio_id=ours)

    moved = client.patch(f"/projects/{project}", json={"portfolio_id": theirs})
    assert moved.status_code == 409, "a project must not change business by patch"
    assert "business" in moved.json()["detail"]
    assert client.get(f"/projects/{project}").json()["portfolio_id"] == ours
    assert client.patch(f"/projects/{project}", json={"portfolio_id": sibling}).status_code == 200


def test_a_projects_responsible_department_must_be_in_its_business(client: TestClient) -> None:
    """The Department report rolls a business's projects up by the department
    accountable for each, so a foreign department files a project's numbers under
    a business that does not own the work. Refused on create and on update."""
    home = _create(client, "/businesses", name="Back Road Creative")
    away = _create(client, "/businesses", name="Other Co")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=home)
    ours = _create(client, "/departments", name="Post", business_id=home)
    foreign = _create(client, "/departments", name="Post", business_id=away)

    body = {"name": "GMS", "portfolio_id": portfolio, "responsible_department_id": foreign}
    created = client.post("/projects", json=body)
    assert created.status_code == 409, "a foreign department must not be accountable on create"
    assert "business" in created.json()["detail"]

    project = _create(
        client, "/projects", name="GMS", portfolio_id=portfolio, responsible_department_id=ours
    )
    strayed = client.patch(f"/projects/{project}", json={"responsible_department_id": foreign})
    assert strayed.status_code == 409, "nor may a patch hand a project to one"
    assert client.get(f"/projects/{project}").json()["responsible_department_id"] == ours


def _probe_portfolio_business(client: TestClient) -> Response:
    home = _create(client, "/businesses", name="Back Road Creative")
    away = _create(client, "/businesses", name="Other Co")
    portfolio = _create(client, "/portfolios", name="Content Brands", business_id=home)
    _create(client, "/programs", name="Video", portfolio_id=portfolio)
    return client.patch(f"/portfolios/{portfolio}", json={"business_id": away})


def _probe_department_business(client: TestClient) -> Response:
    home = _create(client, "/businesses", name="Back Road Creative")
    away = _create(client, "/businesses", name="Other Co")
    department = _create(client, "/departments", name="Post", business_id=home)
    _create(client, "/people", name="JP", department_id=department)
    return client.patch(f"/departments/{department}", json={"business_id": away})


def _probe_program_portfolio(client: TestClient) -> Response:
    business = _create(client, "/businesses", name="Back Road Creative")
    home = _create(client, "/portfolios", name="Home", business_id=business)
    away = _create(client, "/portfolios", name="Away", business_id=business)
    program = _create(client, "/programs", name="Video", portfolio_id=home)
    _create(client, "/projects", name="GMS", portfolio_id=home, program_id=program)
    return client.patch(f"/programs/{program}", json={"portfolio_id": away})


def _portfolio_of(client: TestClient, project: int) -> int:
    return int(client.get(f"/projects/{project}").json()["portfolio_id"])


def _probe_project_portfolio(client: TestClient) -> Response:
    ours, theirs = _sibling_projects(client)
    return client.patch(f"/projects/{ours}", json={"portfolio_id": _portfolio_of(client, theirs)})


def _probe_project_program(client: TestClient) -> Response:
    ours, theirs = _sibling_projects(client)
    foreign = _create(client, "/programs", name="Video", portfolio_id=_portfolio_of(client, theirs))
    return client.patch(f"/projects/{ours}", json={"program_id": foreign})


def _probe_project_department(client: TestClient) -> Response:
    ours, theirs = _sibling_projects(client)
    away = client.get(f"/portfolios/{_portfolio_of(client, theirs)}").json()["business_id"]
    foreign = _create(client, "/departments", name="Post", business_id=away)
    return client.patch(f"/projects/{ours}", json={"responsible_department_id": foreign})


def _probe_workstream_project(client: TestClient) -> Response:
    ours = _seed(client, tag="ours")
    away = client.get(f"/workstreams/{_seed(client, tag='theirs')}").json()["project_id"]
    _create(client, "/tasks", name="Cut", workstream_id=ours)
    return client.patch(f"/workstreams/{ours}", json={"project_id": away})


def _probe_task_workstream(client: TestClient) -> Response:
    task = _create(client, "/tasks", name="Cut", workstream_id=_seed(client, tag="ours"))
    return client.patch(f"/tasks/{task}", json={"workstream_id": _seed(client, tag="theirs")})


def _probe_person_department(client: TestClient) -> tuple[Response, str, int]:
    business = _create(client, "/businesses", name="Back Road Creative")
    post = _create(client, "/departments", name="Post", business_id=business)
    colour = _create(client, "/departments", name="Colour", business_id=business)
    person = _create(client, "/people", name="JP", department_id=post)
    moved = client.patch(f"/people/{person}", json={"department_id": colour})
    return moved, f"/people/{person}", colour


def _probe_task_assignee(client: TestClient) -> tuple[Response, str, int]:
    jp = _create(client, "/people", name="JP")
    ian = _create(client, "/people", name="Ian")
    task = _create(client, "/tasks", name="Cut", workstream_id=_seed(client), assignee_id=jp)
    return client.patch(f"/tasks/{task}", json={"assignee_id": ian}), f"/tasks/{task}", ian


def _probe_issue_risk(client: TestClient) -> Response:
    ours, theirs = _sibling_projects(client)
    issue = _create(client, "/issues", project_id=ours, **_ISSUE)
    return client.patch(f"/issues/{issue}", json={"risk_id": _risk(client, theirs)})


def _probe_change_request_baseline(client: TestClient) -> Response:
    ours, theirs = _sibling_projects(client)
    foreign = _create(client, "/baselines", project_id=theirs, version=1)
    change = _create(client, "/change-requests", project_id=ours, **_CHANGE)
    return client.patch(f"/change-requests/{change}", json={"resulting_baseline_id": foreign})


def _probe_requirement_stakeholder(client: TestClient) -> Response:
    ours, theirs = _sibling_projects(client)
    foreign = _create(client, "/stakeholders", project_id=theirs, name="Stray")
    requirement = _create(
        client, "/requirements", project_id=ours, code="REQ-1", statement="Ship it", actor="qa"
    )
    return client.patch(f"/requirements/{requirement}", json={"source_stakeholder_id": foreign})


def _probe_deliverable_parent(client: TestClient) -> Response:
    ours, theirs = _sibling_projects(client)
    foreign = _create(client, "/deliverables", project_id=theirs, name="Foreign", wbs_code="1")
    deliverable = _create(client, "/deliverables", project_id=ours, name="Cut", wbs_code="1")
    return client.patch(f"/deliverables/{deliverable}", json={"parent_id": foreign})


def _sibling_departments(client: TestClient) -> tuple[int, int]:
    """Two departments in two businesses — ours, and one we must never write into."""
    ours_business = _create(client, "/businesses", name="Back Road Creative")
    theirs_business = _create(client, "/businesses", name="Other Co")
    ours = _create(client, "/departments", name="Post", business_id=ours_business)
    theirs = _create(client, "/departments", name="Post", business_id=theirs_business)
    return ours, theirs


def _probe_work_request_service(client: TestClient) -> Response:
    ours, theirs = _sibling_departments(client)
    foreign = _create(
        client, "/department-services", department_id=theirs, name="Ops desk", owner="Sam"
    )
    request = _create(
        client,
        "/work-requests",
        department_id=ours,
        requester="Grace Hopper",
        raised_on="2026-01-05",
    )
    return client.patch(f"/work-requests/{request}", json={"service_id": foreign})


def _probe_service_level_service(client: TestClient) -> Response:
    ours, theirs = _sibling_departments(client)
    foreign = _create(
        client, "/department-services", department_id=theirs, name="Ops desk", owner="Sam"
    )
    level = _create(
        client, "/service-levels", department_id=ours, measure="turnaround_hours", target=48
    )
    return client.patch(f"/service-levels/{level}", json={"service_id": foreign})


def _probe_estimate_scenario_subject_task(client: TestClient) -> Response:
    ours, theirs = _sibling_projects(client)
    foreign_task = _create(
        client,
        "/tasks",
        name="Stray",
        workstream_id=_create(client, "/workstreams", name="Away", project_id=theirs),
    )
    scenario = _create(
        client,
        "/estimate-scenarios",
        project_id=ours,
        target="duration",
        kind="analogous",
        value=5.0,
        actor="Ada Lovelace",
        as_of="2026-01-05",
    )
    return client.patch(f"/estimate-scenarios/{scenario}", json={"subject_task_id": foreign_task})


def _probe_risk_response_risk(client: TestClient) -> Response:
    ours, theirs = _sibling_projects(client)
    owner = _create(client, "/people", name="Priya")
    response = _create(
        client,
        "/risk-responses",
        project_id=ours,
        risk_id=_risk(client, ours),
        owner_id=owner,
        **_RESPONSE,
    )
    return client.patch(f"/risk-responses/{response}", json={"risk_id": _risk(client, theirs)})


def _probe_risk_response_owner(client: TestClient) -> tuple[Response, str, int]:
    ours, _theirs = _sibling_projects(client)
    priya = _create(client, "/people", name="Priya")
    sam = _create(client, "/people", name="Sam")
    response = _create(
        client,
        "/risk-responses",
        project_id=ours,
        risk_id=_risk(client, ours),
        owner_id=priya,
        **_RESPONSE,
    )
    moved = client.patch(f"/risk-responses/{response}", json={"owner_id": sam})
    return moved, f"/risk-responses/{response}", sam


def _probe_incident_control(client: TestClient) -> Response:
    ours, theirs = _sibling_departments(client)
    foreign = _create(
        client, "/operating-controls", department_id=theirs, name="Ops control", owner="Sam"
    )
    incident = _create(
        client, "/incidents", department_id=ours, description="Late render", raised_on="2026-01-05"
    )
    return client.patch(f"/incidents/{incident}", json={"control_id": foreign})


def _probe_resource_breakdown_parent(client: TestClient) -> Response:
    ours, theirs = _sibling_projects(client)
    our_type = _create(client, "/resource-types", project_id=ours, name="Editor", kind="people")
    their_type = _create(client, "/resource-types", project_id=theirs, name="Editor", kind="people")
    foreign = _create(
        client, "/resource-breakdowns", project_id=theirs, resource_type_id=their_type
    )
    node = _create(client, "/resource-breakdowns", project_id=ours, resource_type_id=our_type)
    return client.patch(f"/resource-breakdowns/{node}", json={"parent_id": foreign})


def _probe_responsibility_assignment_person(client: TestClient) -> tuple[Response, str, int]:
    ours, _theirs = _sibling_projects(client)
    deliverable = _create(client, "/deliverables", project_id=ours, name="Cut", wbs_code="1")
    priya = _create(client, "/people", name="Priya")
    sam = _create(client, "/people", name="Sam")
    assignment = _create(
        client,
        "/responsibility-assignments",
        project_id=ours,
        deliverable_id=deliverable,
        person_id=priya,
        role="responsible",
    )
    moved = client.patch(f"/responsibility-assignments/{assignment}", json={"person_id": sam})
    return moved, f"/responsibility-assignments/{assignment}", sam


def _probe_training_record_person(client: TestClient) -> tuple[Response, str, int]:
    priya = _create(client, "/people", name="Priya")
    sam = _create(client, "/people", name="Sam")
    record = _create(
        client, "/training-records", person_id=priya, topic="Safety", completed_on="2026-01-05"
    )
    moved = client.patch(f"/training-records/{record}", json={"person_id": sam})
    return moved, f"/training-records/{record}", sam


def _probe_conflict_action_owner(client: TestClient) -> tuple[Response, str, int]:
    ours, _theirs = _sibling_projects(client)
    priya = _create(client, "/people", name="Priya")
    sam = _create(client, "/people", name="Sam")
    conflict = _create(
        client,
        "/conflict-records",
        project_id=ours,
        raised_on="2026-01-05",
        parties="Priya, Sam",
        actor="qa",
    )
    action = _create(client, "/conflict-actions", conflict_id=conflict, owner_id=priya)
    moved = client.patch(f"/conflict-actions/{action}", json={"owner_id": sam})
    return moved, f"/conflict-actions/{action}", sam


class MovesFreely(NamedTuple):
    """A link that genuinely points anywhere — proven, never merely asserted.

    The probe performs a real move and returns the PATCH response, the row's
    path and the target id, so the test can require the move to land."""

    probe: Callable[[TestClient], tuple[Response, str, int]]


# Every foreign key a patch twin may keep, and the *proof* it is guarded: a probe
# that drives a real cross-scope write and must be refused, or ``MovesFreely``
# wrapping a probe whose move must visibly land, for a link that genuinely
# points anywhere. Checked against the mapper below, so a model added later — or
# a parent FK spelled with a new name — fails until someone decides whether that
# column may move, guards it, and proves the guard.
Probe = Callable[[TestClient], Response]
_CHECKED_MOVABLE_FK: dict[str, dict[str, Probe | MovesFreely]] = {
    "Portfolio": {"business_id": _probe_portfolio_business},
    "Department": {"business_id": _probe_department_business},
    "Program": {"portfolio_id": _probe_program_portfolio},
    "Project": {
        "portfolio_id": _probe_project_portfolio,
        "program_id": _probe_project_program,
        "responsible_department_id": _probe_project_department,
    },
    "Workstream": {"project_id": _probe_workstream_project},
    "Person": {"department_id": MovesFreely(_probe_person_department)},
    "Task": {
        "assignee_id": MovesFreely(_probe_task_assignee),
        "workstream_id": _probe_task_workstream,
    },
    "Issue": {"risk_id": _probe_issue_risk},
    "RiskResponse": {
        "risk_id": _probe_risk_response_risk,
        "owner_id": MovesFreely(_probe_risk_response_owner),
    },
    "ChangeRequest": {"resulting_baseline_id": _probe_change_request_baseline},
    "WorkRequest": {"service_id": _probe_work_request_service},
    "ServiceLevel": {"service_id": _probe_service_level_service},
    "Incident": {"control_id": _probe_incident_control},
    "EstimateScenario": {"subject_task_id": _probe_estimate_scenario_subject_task},
    "Requirement": {"source_stakeholder_id": _probe_requirement_stakeholder},
    "Deliverable": {"parent_id": _probe_deliverable_parent},
    "ResourceBreakdown": {"parent_id": _probe_resource_breakdown_parent},
    "ResponsibilityAssignment": {"person_id": MovesFreely(_probe_responsibility_assignment_person)},
    "TrainingRecord": {"person_id": MovesFreely(_probe_training_record_person)},
    "ConflictAction": {"owner_id": MovesFreely(_probe_conflict_action_owner)},
}


@pytest.mark.parametrize(
    ("entity", "field"),
    sorted((e, f) for e, fields in _CHECKED_MOVABLE_FK.items() for f in fields),
)
def test_every_movable_fk_refuses_a_cross_scope_write(
    client: TestClient, entity: str, field: str
) -> None:
    """The class-closer: an allowlist entry must *prove* its guard runs.

    Naming the field here used to be the whole test — the comment beside it
    claimed a check and nothing verified one existed. ``Issue.risk_id`` and
    ``ChangeRequest.resulting_baseline_id`` sat here as checked while both write
    paths accepted a row pointed straight across projects. Each entry now carries
    a probe that performs the cross-scope write for real, and the refusal has to
    name what it refuses rather than surface an opaque constraint error.

    A ``MovesFreely`` entry is the mirror-image proof. Its two cases used to
    return without asserting anything, against this very docstring — a guard
    added by mistake, or the field going inert in the patch twin, shipped
    silently. Now the declared-free move has to answer 200, show the new value,
    and still show it on a re-read."""
    probe = _CHECKED_MOVABLE_FK[entity][field]
    if isinstance(probe, MovesFreely):
        moved, row_path, target = probe.probe(client)
        assert moved.status_code == 200, f"{entity}.{field} is declared free-moving: {moved.text}"
        assert moved.json()[field] == target, f"the {entity}.{field} move must visibly happen"
        assert client.get(row_path).json()[field] == target, "and it must land"
        return
    refused = probe(client)
    assert refused.status_code in (409, 422), f"{entity}.{field} took a cross-scope write"
    assert refused.json()["detail"] != "constraint violation", "a refusal names what it refuses"


def test_no_patch_twin_carries_an_unchecked_parent_fk() -> None:
    """Meta-test so the reparent class can never regrow. Freezing FKs *by name*
    was itself the hole: the frozen set spelled the leaf parents
    (``project_id``, ``workstream_id``, ``baseline_id``, ``task_id``), so the
    hierarchy backbone — spelled ``business_id`` and ``portfolio_id`` — walked
    straight past it. This derives the real foreign keys from the SQLAlchemy
    mapper instead, and every one a patch twin keeps must be named above as
    checked-and-movable."""
    patch_names = [name for name in dir(s) if name.endswith("Patch")]
    assert len(patch_names) > 20  # sanity: the whole surface is actually being checked
    for name in patch_names:
        entity = name[: -len("Patch")]
        fks = {c.key for c in sa_inspect(getattr(models, entity)).columns if c.foreign_keys}
        allowed = set(_CHECKED_MOVABLE_FK.get(entity, {}))
        kept = (set(getattr(s, name).model_fields) & fks) - allowed
        assert not kept, f"{name} lets a partial update re-parent a row via {sorted(kept)}"


def test_deleting_an_approved_baseline_is_refused(client: TestClient) -> None:
    """Drain a baseline's lines, approve it, delete it — that would vaporize the
    plan of record with no child left for the generic delete guard to catch. A
    dedicated delete check refuses it, mirroring the baseline-line delete guard.
    An unapproved baseline still deletes once its lines are gone (mistake
    cleanup)."""
    workstream = _seed(client)
    project = client.get(f"/workstreams/{workstream}").json()["project_id"]
    task = _create(client, "/tasks", name="Cut", workstream_id=workstream)
    baseline = _create(client, "/baselines", project_id=project, version=1)
    line = _create(client, "/baseline-lines", **_line(baseline, task))

    assert client.delete(f"/baseline-lines/{line}").status_code == 204
    approval = {"status": "approved", "approved_at": "2026-01-01T09:00:00"}
    assert client.patch(f"/baselines/{baseline}", json=approval).status_code == 200

    refused = client.delete(f"/baselines/{baseline}")
    assert refused.status_code == 409, refused.text
    assert client.get(f"/baselines/{baseline}").status_code == 200, "a refusal changes nothing"


def test_a_baselines_status_and_approval_move_together(client: TestClient) -> None:
    """The freeze keys on ``approved_at``; PMBOK keys on ``status == 'approved'``.
    A partial patch that set one without the other would freeze a plan PMBOK still
    calls draft, or leave PMBOK reporting a plan the freeze still lets anyone edit.
    The API refuses either half alone — approval is one atomic transition."""
    workstream = _seed(client)
    project = client.get(f"/workstreams/{workstream}").json()["project_id"]
    baseline = _create(client, "/baselines", project_id=project, version=1)

    status_only = client.patch(f"/baselines/{baseline}", json={"status": "approved"})
    assert status_only.status_code == 422, "status may not reach 'approved' without approved_at"
    at_only = client.patch(f"/baselines/{baseline}", json={"approved_at": "2026-01-01T09:00:00"})
    assert at_only.status_code == 422, "approved_at may not be set while status stays draft"
    assert client.get(f"/baselines/{baseline}").json()["status"] == "draft", (
        "a refusal changes nothing"
    )

    both = {"status": "approved", "approved_at": "2026-01-01T09:00:00"}
    assert client.patch(f"/baselines/{baseline}", json=both).status_code == 200, (
        "both together is the one atomic approval transition"
    )


def test_a_baseline_cannot_be_created_half_approved(client: TestClient) -> None:
    """The same atomicity holds at create, and holds in the request *type*: a
    create carries every field, so an inconsistent body is unconstructable and no
    route registration has to remember a check. A baseline born
    ``status="approved"`` with no timestamp would be the plan of record to PMBOK
    while a freeze reading the timestamp let anyone edit or delete it."""
    workstream = _seed(client)
    project = client.get(f"/workstreams/{workstream}").json()["project_id"]
    base = {"project_id": project, "version": 1}

    status_only = client.post("/baselines", json={**base, "status": "approved"})
    assert status_only.status_code == 422, "no baseline is born approved without a timestamp"
    at_only = client.post("/baselines", json={**base, "approved_at": "2026-01-01T09:00:00"})
    assert at_only.status_code == 422, "nor approved_at while status stays draft"
    assert client.get("/baselines").json() == [], "a refusal writes nothing"

    # The demo seed's path — create a draft, approve it atomically — still works.
    draft = _create(client, "/baselines", **base)
    approval = {"status": "approved", "approved_at": "2026-01-01T09:00:00"}
    assert client.patch(f"/baselines/{draft}", json=approval).status_code == 200


def test_a_baseline_approved_by_status_alone_is_still_frozen(
    bound: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """Defence in depth: the freeze reads the approval *fact*, not one column.

    Nothing through the API can set ``status="approved"`` without a timestamp any
    more, so this row is written straight to the database — standing in for a
    legacy row or a future path that sets only one signal. It is the plan of
    record either way, so late lines, edits and deletes are all refused.
    """
    client, factory = bound
    workstream = _seed(client)
    project = client.get(f"/workstreams/{workstream}").json()["project_id"]
    task = _create(client, "/tasks", name="Cut", workstream_id=workstream)
    with factory() as db:
        db.add(Baseline(project_id=project, version=1, status="approved"))
        db.commit()
    baseline = int(client.get("/baselines").json()[0]["id"])

    assert client.post("/baseline-lines", json=_line(baseline, task)).status_code == 409
    assert client.patch(f"/baselines/{baseline}", json={"version": 3}).status_code == 409
    assert client.delete(f"/baselines/{baseline}").status_code == 409, "the plan of record stands"


def test_an_open_baseline_still_takes_lines_and_still_deletes(client: TestClient) -> None:
    """The widened freeze must not catch a draft: a still-open baseline takes
    lines, and deletes once they are gone (mistake cleanup)."""
    workstream = _seed(client)
    project = client.get(f"/workstreams/{workstream}").json()["project_id"]
    task = _create(client, "/tasks", name="Cut", workstream_id=workstream)
    baseline = _create(client, "/baselines", project_id=project, version=1)
    line = _create(client, "/baseline-lines", **_line(baseline, task))

    assert client.delete(f"/baseline-lines/{line}").status_code == 204
    assert client.delete(f"/baselines/{baseline}").status_code == 204


# ---- stale-write precondition (If-Match / row_revision) -------------------------


def test_a_patch_with_no_if_match_still_succeeds_unconditionally(client: TestClient) -> None:
    """The omitted header is a deliberate choice (crud._apply), not an oversight: a
    caller that has never adopted the precondition keeps writing exactly as before."""
    task = _create(client, "/tasks", name="Cut", workstream_id=_seed(client))
    patched = client.patch(f"/tasks/{task}", json={"status": "in_progress"})
    assert patched.status_code == 200, patched.text


def test_a_stale_if_match_is_refused_with_409_and_the_current_revision(
    client: TestClient,
) -> None:
    task = _create(client, "/tasks", name="Cut", workstream_id=_seed(client))
    first = client.patch(
        f"/tasks/{task}", json={"status": "in_progress"}, headers={"If-Match": "1"}
    )
    assert first.status_code == 200, first.text

    stale = client.patch(f"/tasks/{task}", json={"status": "done"}, headers={"If-Match": "1"})
    assert stale.status_code == 409, stale.text
    assert "2" in stale.json()["detail"], "the refusal must carry the current revision"
    assert client.get(f"/tasks/{task}").json()["status"] == "in_progress", (
        "a refused write must not land"
    )


def test_a_matching_if_match_succeeds_and_the_revision_keeps_advancing(
    client: TestClient,
) -> None:
    task = _create(client, "/tasks", name="Cut", workstream_id=_seed(client))
    first = client.patch(
        f"/tasks/{task}", json={"status": "in_progress"}, headers={"If-Match": "1"}
    )
    assert first.status_code == 200, first.text
    # The revision advanced past 1, so a second write must now state 2, not 1 again.
    second = client.patch(f"/tasks/{task}", json={"status": "done"}, headers={"If-Match": "2"})
    assert second.status_code == 200, second.text


def test_a_malformed_if_match_is_refused_with_400(client: TestClient) -> None:
    task = _create(client, "/tasks", name="Cut", workstream_id=_seed(client))
    refused = client.patch(
        f"/tasks/{task}", json={"status": "in_progress"}, headers={"If-Match": "not-a-number"}
    )
    assert refused.status_code == 400, refused.text


def test_a_non_object_patch_body_422s_instead_of_crashing_the_frozen_fk_strip(
    client: TestClient,
) -> None:
    """``_dropping_frozen_fk``'s ``_strip`` validator only removes keys off a ``dict``
    body; a JSON array or a bare string passes straight through it unmodified rather
    than calling ``.items()`` on something that has none, and pydantic's own type
    check then answers the 422 — never a 500 off an un-dict-like PATCH body."""
    business = _create(client, "/businesses", name="Back Road Creative")
    for body in (["not", "a", "dict"], "just a string"):
        refused = client.patch(f"/businesses/{business}", json=body)
        assert refused.status_code == 422, refused.text


def test_a_stale_if_match_refuses_a_delete_too(client: TestClient) -> None:
    task = _create(client, "/tasks", name="Cut", workstream_id=_seed(client))
    # advances to revision 2 without a header — the unconditional path still works
    assert client.patch(f"/tasks/{task}", json={"status": "in_progress"}).status_code == 200

    stale = client.delete(f"/tasks/{task}", headers={"If-Match": "1"})
    assert stale.status_code == 409, stale.text
    assert client.get(f"/tasks/{task}").status_code == 200, "a refused delete must not land"

    current = client.delete(f"/tasks/{task}", headers={"If-Match": "2"})
    assert current.status_code == 204, current.text


# ---- row_revision on response models (derived, not hand-listed twice) ----------


def _orm_classes_with_row_revision() -> set[str]:
    """Every ORM class carrying the concurrency token, read off the mappers —
    the same source ``crud._apply`` and ``crud._delete`` check ``If-Match`` against."""
    found: set[str] = set()
    for mapper in Base.registry.mappers:
        if "row_revision" in mapper.columns:
            found.add(mapper.class_.__name__)
    return found


def _out_models_carrying_row_revision() -> set[str]:
    """Every generated ``*Out`` model naming ``row_revision`` among its own
    fields, keyed by the ORM class its name implies (``TaskOut`` -> ``Task``)."""
    found: set[str] = set()
    for name in dir(s):
        if not name.endswith("Out"):
            continue
        model = getattr(s, name)
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            continue
        if "row_revision" in model.model_fields:
            found.add(name[: -len("Out")])
    return found


def test_row_revision_is_on_every_out_model_whose_row_carries_the_column() -> None:
    """PR #194 added the column and the ``If-Match`` check but exposed the value
    nowhere, so a client could only ever learn a revision by first losing a race
    and reading it out of a 409's message text. Both sides here are derived, never
    hand-listed twice: the ORM side reads its own mappers, the schema side reads
    the actual generated ``*Out`` models, and they are compared as an exact set —
    a model that gains the column later, or an ``Out`` model that keeps the field
    after its row loses it, both fail here rather than drifting quietly."""
    has_column = _orm_classes_with_row_revision()
    exposes_it = _out_models_carrying_row_revision()
    assert has_column, "the mapper walk found no row_revision column — the helper is broken"
    assert exposes_it == has_column, sorted(has_column ^ exposes_it)


def test_row_revision_never_appears_on_a_request_or_patch_model() -> None:
    """Server-managed: a client states one back via ``If-Match``, never sets one."""
    checked = 0
    for name in dir(s):
        if not (name.endswith("In") or name.endswith("Patch")):
            continue
        model = getattr(s, name)
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            continue
        checked += 1
        assert "row_revision" not in model.model_fields, name
    assert checked > 20  # sanity: something is actually being checked
