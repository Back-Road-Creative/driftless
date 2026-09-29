"""Balanced-scorecard context for portfolio and program drill pages.

The business Scorecard page owns the complete objective view. This adapter adds
the same objective evidence to a delivery rollup by selecting only contributions
from the projects beneath that node; no project status or metric is averaged into
money-first KPIs.
"""

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from driftless.assess.scorecard import evaluate_metrics
from driftless.calc.rollup import RAG_SEVERITY
from driftless.models import (
    SCORECARD_PERSPECTIVES,
    ScorecardContribution,
    ScorecardMetricDefinition,
    StrategicObjective,
)
from driftless.report.gather import IdTree

PERSPECTIVE_LABELS = {
    "financial": "Financial",
    "customer_stakeholder": "Customer & Stakeholder",
    "internal_operations": "Internal Operations",
    "people_capability": "People & Capability",
}


def _project_ids(branch: IdTree, kind: str) -> tuple[int, ...]:
    """Return project ids from a portfolio/program ``IdTree`` branch."""
    if kind == "program":
        return tuple(child.id for child in branch.children)
    return tuple(
        project.id
        for child in branch.children
        for project in (child.children if child.children else (child,))
    )


def scorecard_rollup(
    db: Session, as_of: date, kind: str, branch: IdTree
) -> tuple[dict[str, Any], ...]:
    """Build four perspective rows for the projects under one delivery node."""
    ids = _project_ids(branch, kind)
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if ids:
        links = db.scalars(
            select(ScorecardContribution)
            .where(ScorecardContribution.project_id.in_(ids))
            .where(ScorecardContribution.status == "active")
            .options(
                selectinload(ScorecardContribution.objective)
                .selectinload(StrategicObjective.metric_definitions)
                .selectinload(ScorecardMetricDefinition.observations),
                selectinload(ScorecardContribution.project),
            )
            .order_by(ScorecardContribution.objective_id, ScorecardContribution.id)
        ).all()
        by_objective: dict[int, dict[str, Any]] = {}
        for link in links:
            objective = link.objective
            row = by_objective.get(objective.id)
            if row is None:
                graded = evaluate_metrics(objective.metric_definitions, as_of)
                evaluations = [evaluation for _, evaluation in graded]
                row = {
                    "objective": objective.name,
                    "perspective": objective.perspective,
                    "status": (
                        max(
                            evaluations,
                            key=lambda evaluation: RAG_SEVERITY[evaluation.status],
                        ).status
                        if evaluations
                        else "unknown"
                    ),
                    "metrics": tuple(
                        {
                            "name": metric.name,
                            "status": evaluation.status,
                            "coverage": evaluation.coverage,
                        }
                        for metric, evaluation in graded
                    ),
                    "projects": [],
                }
                by_objective[objective.id] = row
            if link.project.name not in row["projects"]:
                row["projects"].append(link.project.name)
        for row in by_objective.values():
            rows[row["perspective"]].append(row)
    return tuple(
        {
            "perspective": perspective,
            "label": PERSPECTIVE_LABELS[perspective],
            "objectives": tuple(rows[perspective]),
        }
        for perspective in SCORECARD_PERSPECTIVES
    )
