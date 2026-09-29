"""The balanced-scorecard read model and server-rendered page.

This surface is deliberately separate from the money-first delivery dashboard:
it keeps all four perspectives visible, and it renders missing strategy or
evidence as ``unknown`` rather than turning absence into a green number.
"""

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from driftless.api.deps import get_session
from driftless.assess.scorecard import MetricEvaluation, evaluate_metrics
from driftless.calc.rollup import RAG_SEVERITY
from driftless.models import (
    SCORECARD_PERSPECTIVES,
    ScorecardContribution,
    ScorecardMetricDefinition,
    StrategicObjective,
)
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

Db = Annotated[Session, Depends(get_session)]

PERSPECTIVE_LABELS = {
    "financial": "Financial",
    "customer_stakeholder": "Customer & Stakeholder",
    "internal_operations": "Internal Operations",
    "people_capability": "People & Capability",
}


def _objective_row(objective: StrategicObjective, as_of: date) -> dict[str, Any]:
    graded = evaluate_metrics(objective.metric_definitions, as_of)
    status = _worst([evaluation for _, evaluation in graded])
    return {
        "name": objective.name,
        "owner": objective.owner,
        "lifecycle": objective.status,
        "status": status,
        "metrics": tuple(
            {
                "name": metric.name,
                "unit": metric.unit,
                "evaluation": evaluation,
            }
            for metric, evaluation in graded
        ),
        "projects": tuple(
            contribution.project.name
            for contribution in objective.contributions
            if contribution.status == "active"
        ),
    }


def _worst(metrics: list[MetricEvaluation]) -> str:
    """Fold metric results without allowing missing evidence to appear healthy."""
    if not metrics:
        return "unknown"
    return max(metrics, key=lambda result: RAG_SEVERITY[result.status]).status


def scorecard_rows(db: Session, as_of: date) -> tuple[dict[str, Any], ...]:
    """Build one stable row per perspective, including empty perspectives."""
    objectives = db.scalars(
        select(StrategicObjective)
        .options(
            selectinload(StrategicObjective.metric_definitions).selectinload(
                ScorecardMetricDefinition.observations
            ),
            selectinload(StrategicObjective.contributions).selectinload(
                ScorecardContribution.project
            ),
        )
        .order_by(StrategicObjective.perspective, StrategicObjective.name, StrategicObjective.id)
    ).all()
    return tuple(
        {
            "key": perspective,
            "label": PERSPECTIVE_LABELS[perspective],
            "objectives": tuple(
                _objective_row(objective, as_of)
                for objective in objectives
                if objective.perspective == perspective
            ),
        }
        for perspective in SCORECARD_PERSPECTIVES
    )


def create_scorecard_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """Serve the balanced scorecard with an explicit, reproducible as-of date."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/scorecard", response_class=HTMLResponse)
    def scorecard(request: Request, db: Db, at: date = Depends(resolve_as_of)) -> HTMLResponse:
        rows = scorecard_rows(db, at)
        return TEMPLATES.TemplateResponse(
            request,
            "scorecard.html",
            {
                "as_of": at.isoformat(),
                "rows": rows,
                "has_objectives": any(r["objectives"] for r in rows),
            },
        )

    return router
