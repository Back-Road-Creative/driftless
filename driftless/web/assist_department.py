"""The department workspace: ``GET /org/departments/{department_id}/assist``.

One page, nine sections, each read straight off rows the store already holds —
never a second computation of a figure another page owns. Every section links
its closest technique for READING only, never a launcher: the two techniques
that would honestly fit best — ``resource_optimization`` for demand versus
capacity (reusing ``web.heatmap``'s own leveling rule, ``capacity_cell``, the
same red/amber thresholds the capacity heatmap washes its grid with — ONE
definition of over-allocated, never a second copy) and ``stakeholder_analysis``
for the stakeholder power/interest grid — are ALREADY claimed by a
project-scoped ``Action`` (the schedule and stakeholder evaluators;
``assess.model.ASSISTANT_ROUTES`` keys a route by technique alone, so one
technique cannot point at a project address and a department address at
once). Rather than misroute an unrelated technique to earn a launch mode it
does not deserve, or break the existing project-scoped action's
``launch_href``, every section here stays reference-only.

Objectives, RACI and service levels each note the honest ceiling on what they
compute: scorecard objectives are business-scoped (``models/scorecard.py``),
so "this department's objectives" means the objectives its OWN accountable
projects contribute to, never a department-scoped objective that does not
exist. RACI has no stored responsible/accountable/consulted/informed column
anywhere in the store, so the matrix is assembled from the closest real rows —
a service's ``owner`` (responsible), the department itself (accountable,
``models/people.py``'s own docstring), each accountable project's
``stakeholder_proxy`` ``ProjectRole`` holders (consulted), and the requesters
who raised work against that service (informed) — never an invented
role column. Service levels compare a stored ``target`` against a plain
average cycle time over the service's DONE work requests; the flow
calculators, on a sibling change, are not imported here, so this reads as an
honest average, not a false claim to flow metrics this PR does not carry.

Read-only throughout — nothing here writes. The as-of date is a query
parameter falling back to the default handed to
``create_assist_department_router``, exactly like every other page router: no
wall clock, so a pinned as-of regenerates byte-identically.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.assess.evaluators.resource import person_task_loads
from driftless.assess.scorecard import evaluate_metrics
from driftless.calc import cost as calc_cost
from driftless.calc.control_state import IncidentEvidence, control_state
from driftless.calc.rollup import RAG_SEVERITY
from driftless.models import (
    INCIDENT_SEVERITIES,
    BudgetLine,
    CostEntry,
    Department,
    Project,
    ProjectRole,
    ScorecardContribution,
    StrategicObjective,
)
from driftless.naming import technique_slug
from driftless.pmbok.definitions import TECHNIQUES
from driftless.web.as_of import as_of_dependency
from driftless.web.assist_cost import actual_periods
from driftless.web.departments import name_or_dash, operations_rows
from driftless.web.errors import PageRoute
from driftless.web.heatmap import capacity_cell, hours_label
from driftless.web.templating import TEMPLATES

#: Every technique this page cites — all reference-only (module docstring).
DEMAND_TECHNIQUE = "resource_optimization"
STAKEHOLDER_TECHNIQUE = "stakeholder_analysis"
_RACI_TECHNIQUE = "organizational_theory"
_SERVICE_LEVEL_TECHNIQUE = "quality_improvement_methods"
_CONTROLS_TECHNIQUE = "root_cause_analysis"
_IMPROVEMENTS_TECHNIQUE = "quality_improvement_methods"
_VENDOR_TECHNIQUE = "make_or_buy_analysis"
_BUDGET_TECHNIQUE = "cost_aggregation"
_RUN_RATE_WINDOW = 3  # months — the same trailing window the project cost workbench defaults to


def _technique_ref(key: str) -> dict[str, str]:
    """One technique's display name, page and assistance mode — never a raw key."""
    technique = TECHNIQUES[key]
    return {
        "key": key,
        "display_name": technique.display_name,
        "href": f"/techniques/{technique_slug(key)}",
        "mode": technique.assistance_mode.value,
    }


def _objectives_rows(db: Session, dept: Department, as_of: date) -> list[dict[str, Any]]:
    """Objectives this department's ACCOUNTABLE projects actively contribute to —
    scorecard objectives are business-scoped, so this is the honest reach: never
    a department-scoped objective, because none exists."""
    contributions = db.scalars(
        select(ScorecardContribution)
        .join(Project, ScorecardContribution.project_id == Project.id)
        .where(
            Project.responsible_department_id == dept.id,
            ScorecardContribution.status == "active",
        )
        .options(
            selectinload(ScorecardContribution.objective).selectinload(
                StrategicObjective.metric_definitions
            )
        )
        .order_by(ScorecardContribution.id)
    ).all()
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for link in contributions:
        objective = link.objective
        if objective.id in seen:
            continue
        seen.add(objective.id)
        graded = evaluate_metrics(objective.metric_definitions, as_of)
        status = (
            max(
                (evaluation for _, evaluation in graded), key=lambda e: RAG_SEVERITY[e.status]
            ).status
            if graded
            else "unknown"
        )
        rows.append(
            {
                "objective": objective.name,
                "perspective": objective.perspective,
                "status": status,
                "metrics": tuple(
                    {"name": metric.name, "status": evaluation.status}
                    for metric, evaluation in graded
                ),
            }
        )
    return rows


def _budget_and_run_rate(
    db: Session, dept: Department, project_ids: list[int], as_of: date
) -> dict[str, Any]:
    """The department's own budget lines (``BudgetLine.department_id``) rolled up by
    category, and the run rate of spend on the projects it is accountable for —
    ``calc.cost.run_rate`` over the same monthly buckets the project cost
    workbench prints, across those projects together."""
    lines = db.scalars(
        select(BudgetLine).where(BudgetLine.department_id == dept.id).order_by(BudgetLine.category)
    ).all()
    costs = (
        list(
            db.scalars(
                select(CostEntry)
                .where(CostEntry.project_id.in_(project_ids))
                .order_by(CostEntry.incurred_on, CostEntry.id)
            )
        )
        if project_ids
        else []
    )
    periods = actual_periods(costs, as_of)
    return {
        "lines": [{"category": line.category, "planned": line.planned_amount} for line in lines],
        "total": round(sum(line.planned_amount for line in lines), 2),
        "periods": periods,
        "window": _RUN_RATE_WINDOW,
        "run_rate": round(calc_cost.run_rate(periods, _RUN_RATE_WINDOW), 2) if periods else None,
    }


def _demand_vs_capacity(db: Session, dept: Department) -> dict[str, Any]:
    """Each person's remaining hours against their capacity, classified by the
    SAME rule ``web.heatmap`` washes its grid with — never a second definition
    of over/tight/under. Open work-queue count sits alongside as plain demand
    context, not folded into the ratio: a work request carries no hours
    estimate, so treating a count as hours would be a false unit."""
    people = sorted(dept.people, key=lambda person: person.id)
    loads = person_task_loads(db, [person.id for person in people])
    rows = []
    for person in people:
        _, remaining = loads[person.id]
        cell = capacity_cell(remaining, person.capacity_hours)
        rows.append(
            {
                "name": person.name,
                "capacity": hours_label(person.capacity_hours),
                "remaining_hours": hours_label(remaining),
                "state": cell["state"],
                "mark": cell["mark"],
            }
        )
    open_requests = [
        r for r in dept.work_requests if r.status in ("requested", "queued", "in_progress")
    ]
    return {
        "people": rows,
        "open_work_requests": len(open_requests),
        "total_capacity": hours_label(sum(person.capacity_hours for person in people)),
    }


def _raci_rows(db: Session, dept: Department, project_ids: list[int]) -> list[dict[str, str]]:
    """One row per service: responsible is the service's own owner, accountable
    is the department itself (``models/people.py``'s own docstring), consulted
    is this department's projects' ``stakeholder_proxy`` role holders, informed
    is who raised work against that service."""
    consulted_names = (
        sorted(
            {
                role.holder
                for role in db.scalars(
                    select(ProjectRole).where(
                        ProjectRole.project_id.in_(project_ids),
                        ProjectRole.role == "stakeholder_proxy",
                    )
                )
            }
        )
        if project_ids
        else []
    )
    consulted = ", ".join(consulted_names) if consulted_names else "—"
    rows = []
    for service in sorted(dept.department_services, key=lambda row: row.id):
        informed_names = sorted(
            {req.requester for req in dept.work_requests if req.service_id == service.id}
        )
        rows.append(
            {
                "service": service.name,
                "responsible": service.owner,
                "accountable": dept.name,
                "consulted": consulted,
                "informed": ", ".join(informed_names) if informed_names else "—",
            }
        )
    return rows


def _service_level_rows(dept: Department) -> list[dict[str, str]]:
    """Target versus a plain average cycle time over the service's DONE work
    requests — arithmetic only, no unit conversion pretended between whatever
    ``measure`` names and days."""
    service_names = {service.id: service.name for service in dept.department_services}
    cycles_by_service: dict[int | None, list[int]] = {}
    for request in dept.work_requests:
        if request.status == "done" and request.done_on is not None:
            cycles_by_service.setdefault(request.service_id, []).append(
                (request.done_on - request.raised_on).days
            )
    rows = []
    for level in sorted(dept.service_levels, key=lambda row: row.id):
        cycles = cycles_by_service.get(level.service_id, [])
        measured = (
            f"{sum(cycles) / len(cycles):.1f} days average over {len(cycles)} completed item"
            f"{'s' if len(cycles) != 1 else ''}"
            if cycles
            else "not enough completed work to measure yet"
        )
        rows.append(
            {
                "measure": level.measure,
                "service": name_or_dash(service_names, level.service_id),
                "target": f"{level.target:,.2f}",
                "window": level.window,
                "measured": measured,
            }
        )
    return rows


def _controls_rows(dept: Department, as_of: date) -> list[dict[str, Any]]:
    """Each control's open incidents, the worst severity among them, and its
    computed RAG state — ``calc.control_state``, never a stored status column:
    the same "current state, not a parent record" shape ``models.operations``
    already gives ``OperatingControl`` and ``Incident``."""
    rows = []
    for control in sorted(dept.operating_controls, key=lambda row: row.id):
        open_incidents = [i for i in control.incidents if i.status in ("open", "investigating")]
        worst = (
            max(open_incidents, key=lambda i: INCIDENT_SEVERITIES.index(i.severity)).severity
            if open_incidents
            else "—"
        )
        state = control_state(
            [
                IncidentEvidence(
                    status=i.status,
                    severity=i.severity,
                    raised_on=i.raised_on,
                    resolved_on=i.resolved_on,
                )
                for i in control.incidents
            ],
            as_of,
        )
        rows.append(
            {
                "name": control.name,
                "owner": control.owner,
                "open_incidents": len(open_incidents),
                "worst_severity": worst,
                "state": state.status,
                "reasons": "; ".join(state.reasons),
                "evidence_age_days": (
                    str(state.evidence.age_days)
                    if state.evidence is not None
                    else "no evidence yet"
                ),
            }
        )
    return rows


def _vendor_and_stakeholder_rows(
    projects: list[Project],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Vendor agreements and stakeholders across this department's own
    accountable projects — batched by eager-loading the projects, never one
    query per project."""
    vendors = [
        {
            "vendor": agreement.vendor,
            "project": project.name,
            "amount": f"{agreement.amount:,.2f}",
            "status": agreement.status,
        }
        for project in projects
        for agreement in sorted(project.procurement_agreements, key=lambda a: a.id)
    ]
    stakeholders = [
        {
            "name": stakeholder.name,
            "project": project.name,
            "interest": stakeholder.interest,
            "influence": stakeholder.influence,
            "comms_cadence": stakeholder.comms_cadence,
        }
        for project in projects
        for stakeholder in sorted(project.stakeholders, key=lambda s: s.id)
    ]
    return vendors, stakeholders


def create_assist_department_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The department workspace page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/org/departments/{department_id}/assist", response_class=HTMLResponse)
    def assist_department(
        request: Request, department_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        dept = fetch(db, Department, department_id)
        projects = list(
            db.scalars(
                select(Project)
                .where(Project.responsible_department_id == dept.id)
                .order_by(Project.id)
                .options(
                    selectinload(Project.procurement_agreements), selectinload(Project.stakeholders)
                )
            )
        )
        vendors, stakeholders = _vendor_and_stakeholder_rows(projects)
        context = {
            "department": dept,
            "as_of": at.isoformat(),
            "objectives": _objectives_rows(db, dept, at),
            "operations": operations_rows(dept),
            "raci": _raci_rows(db, dept, [p.id for p in projects]),
            "demand_capacity": _demand_vs_capacity(db, dept),
            "budget": _budget_and_run_rate(db, dept, [p.id for p in projects], at),
            "service_levels": _service_level_rows(dept),
            "controls": _controls_rows(dept, at),
            "vendors": vendors,
            "stakeholders": stakeholders,
            "techniques": {
                "demand_capacity": _technique_ref(DEMAND_TECHNIQUE),
                "stakeholders": _technique_ref(STAKEHOLDER_TECHNIQUE),
                "raci": _technique_ref(_RACI_TECHNIQUE),
                "service_levels": _technique_ref(_SERVICE_LEVEL_TECHNIQUE),
                "controls": _technique_ref(_CONTROLS_TECHNIQUE),
                "improvements": _technique_ref(_IMPROVEMENTS_TECHNIQUE),
                "vendors": _technique_ref(_VENDOR_TECHNIQUE),
                "budget": _technique_ref(_BUDGET_TECHNIQUE),
            },
        }
        return TEMPLATES.TemplateResponse(request, "assist_department.html", context)

    return router
