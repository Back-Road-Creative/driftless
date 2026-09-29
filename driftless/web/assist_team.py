"""The team assist page: ``GET``/``POST /projects/{project_id}/assist/team``.

Routes nine Resource Management techniques (``assess.model.ASSISTANT_ROUTES``):
``organizational_theory``, ``pre_assignment``, ``virtual_teams``, ``colocation``,
``training``, ``team_building``, ``recognition_and_rewards``,
``individual_and_team_assessments`` and ``conflict_management``. The read half is
the RBS as an indented list plus a plain-text twin, the RACI matrix (stored
``ResponsibilityAssignment`` rows), who lacks what (acquisitions still open and
people with no training on record), the team-assessment trend, and open
conflicts with their actions — every figure read straight off the rows
``driftless.pmbok.mapping``'s resource resolvers also read, so this page can
never disagree with them. The three writes this page allows — file an
assignment, record an assessment, log a conflict/action — each go through
``driftless.services.team_writes``, the same validated boundary the JSON
routes use, so the two write paths are one.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.models import (
    Acquisition,
    ConflictAction,
    ConflictRecord,
    Deliverable,
    Person,
    Project,
    ResourceBreakdown,
    ResourceType,
    ResponsibilityAssignment,
    Task,
    TeamAssessment,
    TrainingRecord,
    Workstream,
)
from driftless.pmbok.definitions import TECHNIQUES
from driftless.services.team_writes import (
    file_assignment,
    file_conflict,
    file_conflict_action,
    record_assessment,
)
from driftless.web import csrf, heatmap
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

PROCESS_ID = "9.2"  # Acquire Resources — the RBS/RACI technique this page routes.


def _target_label(assignment: ResponsibilityAssignment) -> str:
    """The one target an assignment names, in words — never more than one, per its CHECK."""
    if assignment.deliverable is not None:
        return f"deliverable: {assignment.deliverable.name}"
    assert assignment.task is not None
    return f"task: {assignment.task.name}"


def _rbs_rows(nodes: list[ResourceBreakdown]) -> list[dict[str, Any]]:
    """The RBS as a depth-first indented list, root nodes first — the same
    "read once, derive on read" shape ``assist_requirements._wbs_rows`` uses
    for the WBS."""
    children: dict[int | None, list[ResourceBreakdown]] = {}
    for node in nodes:
        children.setdefault(node.parent_id, []).append(node)
    for group in children.values():
        group.sort(key=lambda n: n.id)

    rows: list[dict[str, Any]] = []

    def walk(parent_id: int | None, depth: int) -> None:
        for node in children.get(parent_id, ()):
            rows.append({"depth": depth, "node": node})
            walk(node.id, depth + 1)

    walk(None, 0)
    return rows


def _context(db: Session, project: Project, at: date) -> dict[str, Any]:
    resource_types = db.scalars(
        select(ResourceType)
        .where(ResourceType.project_id == project.id)
        .order_by(ResourceType.name)
    ).all()
    rbs_nodes = list(
        db.scalars(
            select(ResourceBreakdown)
            .where(ResourceBreakdown.project_id == project.id)
            .order_by(ResourceBreakdown.id)
        ).all()
    )
    assignments = db.scalars(
        select(ResponsibilityAssignment)
        .where(ResponsibilityAssignment.project_id == project.id)
        .order_by(ResponsibilityAssignment.id)
    ).all()
    acquisitions = db.scalars(
        select(Acquisition)
        .where(Acquisition.project_id == project.id, Acquisition.requested_on <= at)
        .order_by(Acquisition.id)
    ).all()
    open_acquisitions = [a for a in acquisitions if a.status != "fulfilled"]
    people = db.scalars(select(Person).order_by(Person.name)).all()
    trained_ids = {r.person_id for r in db.scalars(select(TrainingRecord))}
    untrained = [p for p in people if p.id not in trained_ids]
    assessments = db.scalars(
        select(TeamAssessment)
        .where(TeamAssessment.project_id == project.id, TeamAssessment.assessed_on <= at)
        .order_by(TeamAssessment.assessed_on, TeamAssessment.id)
    ).all()
    conflicts = db.scalars(
        select(ConflictRecord)
        .where(ConflictRecord.project_id == project.id, ConflictRecord.raised_on <= at)
        .order_by(ConflictRecord.id)
    ).all()
    open_conflicts = [c for c in conflicts if c.resolved_on is None]
    actions = db.scalars(
        select(ConflictAction)
        .join(ConflictRecord, ConflictAction.conflict_id == ConflictRecord.id)
        .where(ConflictRecord.project_id == project.id)
        .order_by(ConflictAction.id)
    ).all()
    actions_by_conflict: dict[int, list[ConflictAction]] = {}
    for action in actions:
        actions_by_conflict.setdefault(action.conflict_id, []).append(action)

    rbs_rows = _rbs_rows(rbs_nodes)
    rbs_text = "\n".join(
        f"{'  ' * row['depth']}{row['node'].resource_type.name} x{row['node'].quantity:g}"
        for row in rbs_rows
    )
    matrix = [
        {"assignment": assignment, "target": _target_label(assignment)}
        for assignment in assignments
    ]

    return {
        "project": project,
        "as_of": at.isoformat(),
        "resource_types": resource_types,
        "rbs_rows": rbs_rows,
        "rbs_text": rbs_text,
        "matrix": matrix,
        "open_acquisitions": open_acquisitions,
        "untrained": untrained,
        "assessments": assessments,
        "open_conflicts": open_conflicts,
        "actions_by_conflict": actions_by_conflict,
        "people": people,
        "deliverables": db.scalars(
            select(Deliverable)
            .where(Deliverable.project_id == project.id)
            .order_by(Deliverable.wbs_code)
        ).all(),
        "tasks": db.scalars(
            select(Task)
            .join(Workstream, Task.workstream_id == Workstream.id)
            .where(Workstream.project_id == project.id)
            .order_by(Task.name)
        ).all(),
        "provenance": {
            "technique": TECHNIQUES["individual_and_team_assessments"].display_name,
            "process": PROCESS_ID,
            "as_of": at.isoformat(),
        },
    }


def create_assist_team_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The team assist page and its three writes, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/assist/team", response_class=HTMLResponse)
    def assist_team(
        request: Request,
        project_id: int,
        db: Db,
        at: date = Depends(resolve_as_of),
        preview_person_id: int | None = None,
        preview_task_id: int | None = None,
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        context = _context(db, project, at)
        context["clash_preview"] = (
            heatmap.clash_preview(db, at, preview_person_id, preview_task_id)
            if preview_person_id is not None and preview_task_id is not None
            else None
        )
        context["preview_person_id"] = preview_person_id
        context["preview_task_id"] = preview_task_id
        return TEMPLATES.TemplateResponse(request, "assist_team.html", context)

    @router.post("/projects/{project_id}/assist/team/assignment")
    def post_assignment(
        request: Request,
        project_id: int,
        db: Db,
        person_id: Annotated[int, Form()],
        deliverable_id: Annotated[int | None, Form()] = None,
        task_id: Annotated[int | None, Form()] = None,
        role: Annotated[str, Form()] = "responsible",
        as_of: Annotated[date | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        csrf.require(request, csrf_token)  # before any read or write
        project = fetch(db, Project, project_id)
        at = resolve_as_of(as_of)
        try:
            payload = s.ResponsibilityAssignmentIn(
                project_id=project.id,
                deliverable_id=deliverable_id,
                task_id=task_id,
                person_id=person_id,
                role=role,  # type: ignore[arg-type]
            )
        except ValidationError as error:
            raise HTTPException(422, str(error)) from error
        file_assignment(db, payload)
        return RedirectResponse(
            f"/projects/{project_id}/assist/team?as_of={at.isoformat()}", status_code=303
        )

    @router.post("/projects/{project_id}/assist/team/assessment")
    def post_assessment(
        request: Request,
        project_id: int,
        db: Db,
        assessed_on: Annotated[date, Form()],
        dimension: Annotated[str, Form()],
        score: Annotated[float, Form()],
        note: Annotated[str | None, Form()] = None,
        actor: Annotated[str, Form()] = "web",
        as_of: Annotated[date | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        csrf.require(request, csrf_token)  # before any read or write
        project = fetch(db, Project, project_id)
        at = resolve_as_of(as_of)
        try:
            payload = s.TeamAssessmentIn(
                project_id=project.id,
                assessed_on=assessed_on,
                dimension=dimension,
                score=score,
                note=note,
                actor=actor or "web",
            )
        except ValidationError as error:
            raise HTTPException(422, str(error)) from error
        record_assessment(db, payload)
        return RedirectResponse(
            f"/projects/{project_id}/assist/team?as_of={at.isoformat()}", status_code=303
        )

    @router.post("/projects/{project_id}/assist/team/conflict")
    def post_conflict(
        request: Request,
        project_id: int,
        db: Db,
        raised_on: Annotated[date, Form()],
        parties: Annotated[str, Form()],
        approach: Annotated[str, Form()] = "collaborate",
        resolved_on: Annotated[date | None, Form()] = None,
        actor: Annotated[str, Form()] = "web",
        as_of: Annotated[date | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        csrf.require(request, csrf_token)  # before any read or write
        project = fetch(db, Project, project_id)
        at = resolve_as_of(as_of)
        try:
            payload = s.ConflictRecordIn(
                project_id=project.id,
                raised_on=raised_on,
                parties=parties,
                approach=approach,  # type: ignore[arg-type]
                resolved_on=resolved_on,
                actor=actor or "web",
            )
        except ValidationError as error:
            raise HTTPException(422, str(error)) from error
        file_conflict(db, payload)
        return RedirectResponse(
            f"/projects/{project_id}/assist/team?as_of={at.isoformat()}", status_code=303
        )

    @router.post("/projects/{project_id}/assist/team/action")
    def post_action(
        request: Request,
        project_id: int,
        db: Db,
        conflict_id: Annotated[int, Form()],
        owner_id: Annotated[int, Form()],
        due_on: Annotated[date | None, Form()] = None,
        as_of: Annotated[date | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        csrf.require(request, csrf_token)  # before any read or write
        fetch(db, Project, project_id)
        at = resolve_as_of(as_of)
        try:
            payload = s.ConflictActionIn(conflict_id=conflict_id, owner_id=owner_id, due_on=due_on)
        except ValidationError as error:
            raise HTTPException(422, str(error)) from error
        file_conflict_action(db, payload)
        return RedirectResponse(
            f"/projects/{project_id}/assist/team?as_of={at.isoformat()}", status_code=303
        )

    return router
