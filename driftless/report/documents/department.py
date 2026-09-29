"""The Department Report: the business rolled up by the department accountable for
each project. Business-scoped (``SCOPE = "business"``), so the CLI renders it once
with ``render(session, as_of)``. For each department it lists headcount, weekly
capacity and the capacity-weighted blended labour rate of its people, and the
projects it owns with their earned-value budget, actual and CPI — every figure
from ``driftless.calc`` via the shared adapter.
Collections are ORDER BY-sorted and numbers pre-formatted, so
the same store regenerates byte-identically."""

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.models import Department, Project
from driftless.report import engine, gather

SLUG = "department"
TITLE = "Department Report"
SCOPE = "business"


def department_rows(session: Session, as_of: date) -> list[dict[str, Any]]:
    """Per-department figures as of ``as_of`` — public, and reused verbatim by
    ``driftless.web.departments`` so the report and the dash cannot disagree.
    ``id`` rides along for the web surface's drill links; unused by the doc.

    Costs are batched once via ``gather.project_costs`` — the same pre-fetched
    map ``gather.project_evm`` (a thin wrapper over ``adapters.snapshot_from``)
    already expects — instead of ``adapters.project_snapshot``'s one
    ``select(CostEntry)`` per project; that turned every department's project
    list into an N+1 (``tests/test_web_departments.py``'s statement ceiling)."""
    rows: list[dict[str, Any]] = []
    costs = gather.project_costs(session)
    departments = session.scalars(select(Department).order_by(Department.name, Department.id))
    for dept in departments:
        people = sorted(dept.people, key=lambda person: person.id)
        projects = session.scalars(
            select(Project)
            .where(Project.responsible_department_id == dept.id)
            .order_by(Project.name, Project.id)
            .options(*adapters.eager_project())
        )
        project_rows = []
        for project in projects:
            snap = gather.project_evm(project, costs.get(project.id, []), as_of)
            project_rows.append(
                {
                    "id": project.id,
                    "name": project.name,
                    "budget": f"{snap.bac:,.0f}",
                    "actual": f"{snap.ac:,.0f}",
                    "cpi": f"{snap.cpi:.2f}" if snap.cpi is not None else "n/a",
                }
            )
        # Capacity-weighted: hours are what a department supplies, so the blend is
        # what an average supplied hour costs — a head-average priced a 5-hour
        # specialist as a 40-hour supply. Zero total capacity means no people.
        capacity_hours = sum(p.capacity_hours for p in people)
        blended = (
            sum(p.cost_rate * p.capacity_hours for p in people) / capacity_hours
            if capacity_hours
            else 0.0
        )
        rows.append(
            {
                "id": dept.id,
                "name": dept.name,
                "business": dept.business.name,
                "headcount": len(people),
                "capacity_hours": f"{capacity_hours:,.0f}",
                # Unformatted, so the web list can total it without re-parsing.
                "capacity_hours_value": capacity_hours,
                "blended_rate": f"{blended:,.2f}",
                "projects": project_rows,
            }
        )
    return rows


def render(session: Session, as_of: date) -> str:
    """Render the business-wide Department Report as of ``as_of``."""
    return engine.render(
        "department.md",
        {"title": TITLE, "as_of": as_of, "departments": department_rows(session, as_of)},
    )
