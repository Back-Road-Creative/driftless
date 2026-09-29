"""One page per project: ``/projects/{project_id}/hub`` — the project hub.

Composes a project's health at a glance from the SAME engines the sibling pages
render from — gather's EVM adapter (via ``views.evm_curve``), the shared view helpers' threat
cards scoped to this project (``views.threat_cards(db, at, project_id=...)`` —
this project's assessment only, never the whole store's), and per-area
completeness — plus scoped RAID counts and milestones, with the three deep pages
(process map, wizard, weekly status) linked as its sections. Adapts and renders
only — no figure the engines own is recomputed — and reads no wall clock, so a
pinned as-of regenerates byte-identically. The bare ``/projects/{id}`` path
belongs to the JSON API's project read (registered first, so it always wins the
match); ``/hub`` keeps the API contract intact while giving the browser page its
own address.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.assess import adapters
from driftless.assess.evaluators.schedule import milestone_slipped
from driftless.assess.scorecard import evaluate_metrics
from driftless.calc.evidence_age import evidence_age
from driftless.calc.rollup import RAG_SEVERITY
from driftless.models import (
    ChangeRequest,
    Issue,
    Milestone,
    Project,
    Risk,
    ScorecardContribution,
    ScorecardMetricDefinition,
    StrategicObjective,
)
from driftless.pmbok import flow_facts, risk_facts, state
from driftless.report import gather
from driftless.web.views import area_completeness, evm_curve, pct, threat_cards
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.receipt import attach_receipt
from driftless.web.templating import TEMPLATES

# "Open" per RAID model — risks reuse gather's OPEN_RISKS definition:
OPEN_ISSUES = ("open", "in_progress")  # an issue is open until resolved/closed
OPEN_CHANGES = ("proposed",)  # a change request is open only while proposed


def _open_count(
    db: Session,
    model: type[Risk | Issue | ChangeRequest],
    project_id: int,
    statuses: tuple[str, ...],
) -> int:
    """One RAID model's open-row count, scoped to the project — a plain aggregate."""
    where = (model.project_id == project_id, model.status.in_(statuses))
    return int(db.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def _scorecard_lenses(db: Session, project_id: int, as_of: date) -> list[dict[str, Any]]:
    """Adapt this project's active objective links and derived metric statuses."""
    links = db.scalars(
        select(ScorecardContribution)
        .where(ScorecardContribution.project_id == project_id)
        .where(ScorecardContribution.status == "active")
        .options(
            selectinload(ScorecardContribution.objective)
            .selectinload(StrategicObjective.metric_definitions)
            .selectinload(ScorecardMetricDefinition.observations)
        )
        .order_by(ScorecardContribution.id)
    ).all()
    lenses: list[dict[str, Any]] = []
    for link in links:
        graded = evaluate_metrics(link.objective.metric_definitions, as_of)
        status = (
            max((e for _, e in graded), key=lambda e: RAG_SEVERITY[e.status]).status
            if graded
            else "unknown"
        )
        lenses.append(
            {
                "perspective": link.objective.perspective,
                "objective": link.objective.name,
                "contribution_type": link.contribution_type,
                "status": status,
                "metrics": tuple(
                    {
                        "name": metric.name,
                        "status": evaluation.status,
                        "coverage": evaluation.coverage,
                    }
                    for metric, evaluation in graded
                ),
            }
        )
    return lenses


def _flow_tile(db: Session, project: Project, at: date) -> dict[str, Any]:
    """The flow tile row: WIP, throughput per week, median cycle time and the
    release forecast — one plain sentence each, from ``pmbok.flow_facts`` (the
    same adapter the flow page reads, so the two can never disagree)."""
    snap = flow_facts.flow_snapshot(db, project, at)
    cycle_median = snap.cycle_time.median
    return {
        "wip": snap.wip,
        "throughput": snap.throughput,
        "cycle_time_median": cycle_median,
        "forecast_likely": snap.forecast.likely if snap.forecast else None,
    }


def create_project_hub_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The per-project hub page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/hub", response_class=HTMLResponse)
    def project_hub(
        request: Request, project_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        # Scoped, never store-wide: this is a ONE-project page, and gather's
        # batched full-table read would hand it every project's spend.
        costs = adapters.project_costs(db, project)
        # One prefetch scope: project_process_states is computed ONCE and threaded
        # into area_completeness, mirroring pages.process_map; state.completeness's
        # own walk rides the same cache (pmbok.state.prefetched).
        with state.prefetched(db, [project]):
            states = state.project_process_states(project, db, at)
            rings = area_completeness(states)
            completeness = pct(state.completeness(project, db, at))
        milestones = [
            {
                "name": m.name,
                "target": m.target_date.isoformat(),
                "status": m.status,
                "slipped": milestone_slipped(m, at),
            }
            for m in db.scalars(
                select(Milestone)
                .where(Milestone.project_id == project.id)
                .order_by(Milestone.target_date, Milestone.id)
            )
        ]
        lenses = _scorecard_lenses(db, project.id, at)
        # evm_curve carries only ev/cpi/spi/eac; CV/SV need ac/pv, so this reads
        # ``costs`` again through the canonical adapter rather than widening its dict.
        snap = adapters.snapshot_from(project, costs, at)
        context: dict[str, Any] = {
            "project": project,
            "as_of": at.isoformat(),
            "completeness": completeness,
            "ring_labels": {area: pct(frac) for area, frac in rings.items()},
            "evm": evm_curve(project, costs, at),
            "cv": round(snap.cv, 2),
            "sv": round(snap.sv, 2),
            "cv_words": "under budget" if snap.cv >= 0 else "over budget",
            "sv_words": "ahead of plan" if snap.sv >= 0 else "behind plan",
            "threats": threat_cards(db, at, project_id=project.id),
            "raid": {
                "risks": _open_count(db, Risk, project.id, gather.OPEN_RISKS),
                "issues": _open_count(db, Issue, project.id, OPEN_ISSUES),
                "changes": _open_count(db, ChangeRequest, project.id, OPEN_CHANGES),
            },
            "milestones": milestones,
            "scorecard_lenses": lenses,
            # The reserve line 5.6 propagates into the cost workbench: the same
            # residual-exposure figure the risk-response planner and the risk
            # report both read, never a second computation.
            "risk_reserve_suggested": risk_facts.gather(db, project, at).residual_exposure,
            "flow": _flow_tile(db, project, at),
            # The evidence behind the EVM figures above: every cost entry's own
            # posting date -- the record kind the earned-value curve is swept from.
            "evidence": evidence_age(at, [c.incurred_on for c in costs]),
        }
        response = TEMPLATES.TemplateResponse(request, "project_hub.html", context)
        return attach_receipt(response, at)

    @router.get("/projects/{project_id}/hub/costs", response_class=HTMLResponse)
    def hub_cost_inputs(
        request: Request, project_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        """The read-only provenance page behind the EVM figures on both the hub and
        the weekly-status page: every CostEntry this project's actual cost is swept
        from, filtered to ``incurred_on <= at`` -- the same bound ``calc.evm.actual_cost``
        applies, so the rows listed here are exactly the ones the EV/CPI/SPI/EAC/CV/SV
        figures were computed from, never the project's whole cost history."""
        project = fetch(db, Project, project_id)
        costs = [c for c in adapters.project_costs(db, project) if c.incurred_on <= at]
        context = {
            "project": project,
            "as_of": at.isoformat(),
            "costs": costs,
        }
        response = TEMPLATES.TemplateResponse(request, "hub_cost_inputs.html", context)
        return attach_receipt(response, at)

    return router
