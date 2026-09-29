"""The department web surface: ``GET /org/departments`` (list) and
``GET /org/departments/{department_id}`` (drill).

The pages sit under ``/org`` because the bare ``/departments`` path belongs to
the JSON CRUD API, which ``driftless.api.app`` registers before ``mount_web``
includes this router — FastAPI matches in registration order, so a page on the
entity path would be answered with JSON and never render. Same convention as
``/projects/{id}/hub`` and ``/portfolios/{id}/rollup``;
``tests/test_web_routes_not_shadowed.py`` holds the whole class.

The list renders from ``department_rows`` — the SAME per-department
computation the Department report document renders from, so a figure on
screen can never disagree with the document. The drill page shows ONE
department, so it must not rebuild the whole org's rows to find its own:
:func:`_department_row` computes the same row from the same engines
(``gather.project_evm`` for every EVM figure, ``adapters.eager_project`` for
the baseline walk, costs batched across the department's projects by the
``adapters.prefetched`` scope), scoped to the drilled department — the
agreement test pins its rendered figures to the report document's. Its
per-person rows reuse the Resource evaluator's ``person_task_loads`` rather
than a second remaining-hours definition. The as-of date is a query parameter
falling back to the default handed to ``create_departments_router``, exactly
like ``driftless.web.home`` and every other page router — no wall clock.

The drill page also lists the department's own operating records
(``driftless.models.operations``): services, the work queue, recurring work,
SLAs, controls, incidents and improvements — one read per collection off the
already-loaded ``dept``, never a per-row lookup: a work request's or service
level's linked service NAME, and an incident's linked control NAME, are read
out of a dict built from the department's own (already-fetched) service and
control lists rather than by touching the ``.service``/``.control``
relationship on each row, which is what would turn a fixed handful of
statements into one per row shown.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.deps import get_session
from driftless.assess import adapters
from driftless.assess.evaluators.resource import person_task_loads
from driftless.models import ArtifactLink, Department, Note, Project
from driftless.report import gather
from driftless.report.documents.department import department_rows
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

Db = Annotated[Session, Depends(get_session)]


def _department_row(db: Session, dept: Department, as_of: date) -> dict[str, Any]:
    """One department's row — ``department_rows``'s figures, computed for this
    department alone. Same engines, so the drill cannot disagree with the
    document: ``gather.project_evm`` (the canonical EVM adapter) per project,
    ``adapters.eager_project`` collapsing the Baseline → Line → Task walk, and
    one ``adapters.project_costs`` read batched across the department's
    projects by the ``adapters.prefetched`` scope — never ``gather``'s
    store-wide cost scan, and never another department's rows."""
    people = sorted(dept.people, key=lambda person: person.id)
    projects = list(
        db.scalars(
            select(Project)
            .where(Project.responsible_department_id == dept.id)
            .order_by(Project.name, Project.id)
            .options(*adapters.eager_project())
        )
    )
    project_rows: list[dict[str, str]] = []
    with adapters.prefetched(db, projects):
        for project in projects:
            snap = gather.project_evm(project, adapters.project_costs(db, project), as_of)
            project_rows.append(
                {
                    "name": project.name,
                    "budget": f"{snap.bac:,.0f}",
                    "actual": f"{snap.ac:,.0f}",
                    "cpi": f"{snap.cpi:.2f}" if snap.cpi is not None else "no data yet",
                }
            )
    blended = (sum(p.cost_rate for p in people) / len(people)) if people else 0.0
    return {
        "id": dept.id,
        "name": dept.name,
        "business": dept.business.name,
        "headcount": len(people),
        "capacity_hours": f"{sum(p.capacity_hours for p in people):,.0f}",
        "blended_rate": f"{blended:,.2f}",
        "projects": project_rows,
    }


def name_or_dash(names: dict[int, str], key: int | None) -> str:
    """A linked row's name, or an em dash for no link — never a raised ``KeyError``.

    Public: shared with ``web.assist_department``, which looks up a service
    name off the same kind of dict this module builds — one definition of
    "no link" rather than a second copy per caller."""
    return "—" if key is None else names.get(key, "—")


def operations_rows(dept: Department) -> dict[str, list[dict[str, str]]]:
    """The department's own operating records, one section per table, in plain
    words. Each collection is read off ``dept`` exactly once — see the module
    docstring for why a linked service/control name is looked up in a dict
    built from that same read rather than through its own relationship.

    Public: ``web.assist_department`` reuses this for its operating-plan and
    improvements sections rather than re-reading the same collections."""
    services = sorted(dept.department_services, key=lambda row: row.id)
    controls = sorted(dept.operating_controls, key=lambda row: row.id)
    service_names = {service.id: service.name for service in services}
    control_names = {control.id: control.name for control in controls}
    return {
        "department_services": [
            {"name": row.name, "owner": row.owner, "description": row.description}
            for row in services
        ],
        "work_requests": [
            {
                "requester": row.requester,
                "service": name_or_dash(service_names, row.service_id),
                "priority": row.priority,
                "status": row.status,
                "raised_on": row.raised_on.isoformat(),
            }
            for row in sorted(dept.work_requests, key=lambda row: row.id)
        ],
        "recurring_work_items": [
            {
                "name": row.name,
                "cadence": row.cadence,
                "owner": row.owner,
                "next_due_on": row.next_due_on.isoformat() if row.next_due_on else "—",
            }
            for row in sorted(dept.recurring_work_items, key=lambda row: row.id)
        ],
        "service_levels": [
            {
                "measure": row.measure,
                "service": name_or_dash(service_names, row.service_id),
                "target": f"{row.target:,.2f}",
                "window": row.window,
            }
            for row in sorted(dept.service_levels, key=lambda row: row.id)
        ],
        "operating_controls": [
            {"name": row.name, "owner": row.owner, "description": row.description}
            for row in controls
        ],
        "incidents": [
            {
                "description": row.description,
                "control": name_or_dash(control_names, row.control_id),
                "severity": row.severity,
                "status": row.status,
                "raised_on": row.raised_on.isoformat(),
            }
            for row in sorted(dept.incidents, key=lambda row: row.id)
        ],
        "improvements": [
            {"what": row.what, "owner": row.owner, "status": row.status}
            for row in sorted(dept.improvements, key=lambda row: row.id)
        ],
    }


def create_departments_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The department list and drill pages, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/org/departments", response_class=HTMLResponse)
    def departments(request: Request, db: Db, at: date = Depends(resolve_as_of)) -> HTMLResponse:
        rows = department_rows(db, at)
        # Totals summed in code from the rows the table shows, never a second query.
        totals = {
            "count": len(rows),
            "headcount": sum(row["headcount"] for row in rows),
            "capacity_hours": f"{sum(row['capacity_hours_value'] for row in rows):,.0f}",
        }
        context = {"as_of": at.isoformat(), "departments": rows, "totals": totals}
        return TEMPLATES.TemplateResponse(request, "departments.html", context)

    @router.get("/org/departments/{department_id}", response_class=HTMLResponse)
    def department_detail(
        request: Request, department_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        dept = db.get(Department, department_id)
        if dept is None:
            raise HTTPException(404, f"department {department_id} not found")
        row = _department_row(db, dept, at)
        roster = sorted(dept.people, key=lambda p: p.id)
        loads = person_task_loads(db, [person.id for person in roster])
        people: list[dict[str, int | str]] = []
        for person in roster:
            open_tasks, remaining_hours = loads[person.id]
            people.append(
                {
                    "name": person.name,
                    "capacity_hours": f"{person.capacity_hours:,.0f}",
                    "open_tasks": open_tasks,
                    "remaining_hours": f"{remaining_hours:,.0f}",
                }
            )
        links = db.scalars(
            select(ArtifactLink)
            .where(ArtifactLink.record_kind == "department", ArtifactLink.record_id == str(dept.id))
            .order_by(ArtifactLink.id)
        )
        notes = db.scalars(
            select(Note)
            .where(Note.record_kind == "department", Note.record_id == str(dept.id))
            .order_by(Note.id)
        )
        context = {
            "as_of": at.isoformat(),
            "department": row,
            "people": people,
            "operations": operations_rows(dept),
            "artifact_links": [{"uri": link.uri, "title": link.title} for link in links],
            "notes": [{"body": note.body, "actor": note.actor} for note in notes],
        }
        return TEMPLATES.TemplateResponse(request, "department_detail.html", context)

    return router
