"""The department web surface: ``GET /org/departments`` (list) and
``GET /org/departments/{department_id}`` (drill).

The pages sit under ``/org`` because the bare ``/departments`` path belongs to
the JSON CRUD API, which ``driftless.api.app`` registers before ``_mount_web``
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
like ``driftless.web.home`` and ``driftless.web.pages`` — no wall clock.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.app import get_session
from driftless.assess import adapters
from driftless.assess.evaluators.resource import person_task_loads
from driftless.models import Department, Project
from driftless.report import gather
from driftless.report.documents.department import department_rows
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
                    "cpi": f"{snap.cpi:.2f}" if snap.cpi is not None else "n/a",
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


def create_departments_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The department list and drill pages, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve = default_as_of if callable(default_as_of) else lambda: default_as_of

    @router.get("/org/departments", response_class=HTMLResponse)
    def departments(request: Request, db: Db, as_of: date | None = None) -> HTMLResponse:
        at = as_of or resolve()
        context = {"as_of": at.isoformat(), "departments": department_rows(db, at)}
        return TEMPLATES.TemplateResponse(request, "departments.html", context)

    @router.get("/org/departments/{department_id}", response_class=HTMLResponse)
    def department_detail(
        request: Request, department_id: int, db: Db, as_of: date | None = None
    ) -> HTMLResponse:
        dept = db.get(Department, department_id)
        if dept is None:
            raise HTTPException(404, f"department {department_id} not found")
        at = as_of or resolve()
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
        context = {"as_of": at.isoformat(), "department": row, "people": people}
        return TEMPLATES.TemplateResponse(request, "department_detail.html", context)

    return router
