"""The requirements/WBS worksheet: ``GET``/``POST /projects/{project_id}/assist/requirements``.

Routes ``decomposition`` (``assess.model.ASSISTANT_ROUTES``), 5.4 Create WBS's own
technique. The read half is the traceability matrix (requirements against
deliverables/tasks/backlog items), the untraced requirements and orphan
deliverables named in words, the WBS as an indented list plus a plain-text twin,
and the acceptance ledger — every figure read straight off the rows
``driftless.pmbok.mapping``'s scope resolvers also read, so this page can never
disagree with them. The three writes this page allows — file a requirement, file
a trace, record acceptance — each go through
``driftless.services.scope_writes``, the same validated boundary the JSON routes
use, so the two write paths are one.
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
    AcceptanceRecord,
    BacklogItem,
    Deliverable,
    Project,
    Requirement,
    RequirementTrace,
    Stakeholder,
    Task,
    Workstream,
)
from driftless.pmbok.definitions import TECHNIQUES
from driftless.services.scope_writes import (
    file_requirement,
    file_requirement_trace,
    record_acceptance,
)
from driftless.web import csrf
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

PROCESS_ID = "5.4"  # Create WBS — the technique this page routes is its tool.


def _target_label(trace: RequirementTrace) -> str:
    """The one target a trace names, in words — never more than one, per its CHECK."""
    if trace.deliverable is not None:
        return f"deliverable: {trace.deliverable.name}"
    if trace.task is not None:
        return f"task: {trace.task.name}"
    assert trace.backlog_item is not None
    return f"backlog item: {trace.backlog_item.title}"


def _wbs_rows(deliverables: list[Deliverable]) -> list[dict[str, Any]]:
    """The WBS as a depth-first indented list, root nodes first in ``wbs_code`` order.

    Built from an in-memory tree rather than a recursive query — the whole
    project's node count is small enough that one read plus a Python walk is
    simpler than a recursive CTE, and it is the same "read once, derive on read"
    shape every other rollup in this codebase uses.
    """
    children: dict[int | None, list[Deliverable]] = {}
    for node in deliverables:
        children.setdefault(node.parent_id, []).append(node)
    for group in children.values():
        group.sort(key=lambda n: n.wbs_code)

    rows: list[dict[str, Any]] = []

    def walk(parent_id: int | None, depth: int) -> None:
        for node in children.get(parent_id, ()):
            rows.append({"depth": depth, "node": node})
            walk(node.id, depth + 1)

    walk(None, 0)
    return rows


def _context(db: Session, project: Project, at: date) -> dict[str, Any]:
    requirements = db.scalars(
        select(Requirement).where(Requirement.project_id == project.id).order_by(Requirement.code)
    ).all()
    traces = db.scalars(
        select(RequirementTrace)
        .join(Requirement, RequirementTrace.requirement_id == Requirement.id)
        .where(Requirement.project_id == project.id)
        .order_by(RequirementTrace.id)
    ).all()
    deliverables = list(
        db.scalars(
            select(Deliverable)
            .where(Deliverable.project_id == project.id)
            .order_by(Deliverable.wbs_code)
        ).all()
    )
    ledger = db.scalars(
        select(AcceptanceRecord)
        .join(Deliverable, AcceptanceRecord.deliverable_id == Deliverable.id)
        .where(Deliverable.project_id == project.id)
        .order_by(AcceptanceRecord.id)
    ).all()

    matrix = [
        {"requirement": trace.requirement, "trace": trace, "target": _target_label(trace)}
        for trace in traces
    ]
    traced_requirement_ids = {trace.requirement_id for trace in traces}
    untraced = [r for r in requirements if r.id not in traced_requirement_ids]
    traced_deliverable_ids = {
        trace.deliverable_id for trace in traces if trace.deliverable_id is not None
    }
    orphan_deliverables = [d for d in deliverables if d.id not in traced_deliverable_ids]

    wbs_rows = _wbs_rows(deliverables)
    wbs_text = "\n".join(
        f"{'  ' * row['depth']}{row['node'].wbs_code} {row['node'].name}" for row in wbs_rows
    )

    return {
        "project": project,
        "as_of": at.isoformat(),
        "requirements": requirements,
        "matrix": matrix,
        "untraced": untraced,
        "orphan_deliverables": orphan_deliverables,
        "deliverables": deliverables,
        "wbs_rows": wbs_rows,
        "wbs_text": wbs_text,
        "ledger": ledger,
        "stakeholders": db.scalars(
            select(Stakeholder)
            .where(Stakeholder.project_id == project.id)
            .order_by(Stakeholder.name)
        ).all(),
        "tasks": db.scalars(
            select(Task)
            .join(Workstream, Task.workstream_id == Workstream.id)
            .where(Workstream.project_id == project.id)
            .order_by(Task.name)
        ).all(),
        "backlog_items": db.scalars(
            select(BacklogItem)
            .where(BacklogItem.project_id == project.id)
            .order_by(BacklogItem.title)
        ).all(),
        "provenance": {
            "technique": TECHNIQUES["decomposition"].display_name,
            "process": PROCESS_ID,
            "as_of": at.isoformat(),
        },
    }


def create_assist_requirements_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The requirements/WBS worksheet page and its three writes, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/assist/requirements", response_class=HTMLResponse)
    def assist_requirements(
        request: Request, project_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        context = _context(db, project, at)
        return TEMPLATES.TemplateResponse(request, "assist_requirements.html", context)

    @router.post("/projects/{project_id}/assist/requirements/requirement")
    def post_requirement(
        request: Request,
        project_id: int,
        db: Db,
        code: Annotated[str, Form()],
        statement: Annotated[str, Form()],
        category: Annotated[str, Form()] = "functional",
        priority: Annotated[str, Form()] = "should_have",
        source_stakeholder_id: Annotated[int | None, Form()] = None,
        status: Annotated[str, Form()] = "proposed",
        actor: Annotated[str, Form()] = "web",
        as_of: Annotated[date | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        csrf.require(request, csrf_token)  # before any read or write
        project = fetch(db, Project, project_id)
        at = resolve_as_of(as_of)
        try:
            payload = s.RequirementIn(
                project_id=project.id,
                code=code,
                statement=statement,
                category=category,  # type: ignore[arg-type]
                priority=priority,  # type: ignore[arg-type]
                source_stakeholder_id=source_stakeholder_id,
                status=status,  # type: ignore[arg-type]
                actor=actor or "web",
            )
        except ValidationError as error:
            raise HTTPException(422, str(error)) from error
        file_requirement(db, payload)
        return RedirectResponse(
            f"/projects/{project_id}/assist/requirements?as_of={at.isoformat()}", status_code=303
        )

    @router.post("/projects/{project_id}/assist/requirements/trace")
    def post_trace(
        request: Request,
        project_id: int,
        db: Db,
        requirement_id: Annotated[int, Form()],
        deliverable_id: Annotated[int | None, Form()] = None,
        task_id: Annotated[int | None, Form()] = None,
        backlog_item_id: Annotated[int | None, Form()] = None,
        as_of: Annotated[date | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        csrf.require(request, csrf_token)  # before any read or write
        fetch(db, Project, project_id)
        at = resolve_as_of(as_of)
        try:
            payload = s.RequirementTraceIn(
                requirement_id=requirement_id,
                deliverable_id=deliverable_id,
                task_id=task_id,
                backlog_item_id=backlog_item_id,
            )
        except ValidationError as error:
            raise HTTPException(422, str(error)) from error
        file_requirement_trace(db, payload)
        return RedirectResponse(
            f"/projects/{project_id}/assist/requirements?as_of={at.isoformat()}", status_code=303
        )

    @router.post("/projects/{project_id}/assist/requirements/acceptance")
    def post_acceptance(
        request: Request,
        project_id: int,
        db: Db,
        deliverable_id: Annotated[int, Form()],
        verified_on: Annotated[date | None, Form()] = None,
        accepted_on: Annotated[date | None, Form()] = None,
        actor: Annotated[str, Form()] = "web",
        note: Annotated[str | None, Form()] = None,
        as_of: Annotated[date | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        csrf.require(request, csrf_token)  # before any read or write
        fetch(db, Project, project_id)
        at = resolve_as_of(as_of)
        try:
            payload = s.AcceptanceRecordIn(
                deliverable_id=deliverable_id,
                verified_on=verified_on,
                accepted_on=accepted_on,
                actor=actor or "web",
                note=note,
            )
        except ValidationError as error:
            raise HTTPException(422, str(error)) from error
        record_acceptance(db, payload)
        return RedirectResponse(
            f"/projects/{project_id}/assist/requirements?as_of={at.isoformat()}", status_code=303
        )

    return router
