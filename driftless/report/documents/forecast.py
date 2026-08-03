"""The Forecast Report: where a project is heading. A predictive project gets the
EVM completion forecast (EAC/ETC/VAC) and milestone slip against baseline; an agile
one gets the velocity-band completion forecast from its sprint history; a hybrid one
gets both. All share the risk exposure weighed against the held contingency, from
``driftless.assess.exposure`` — the one engine the Risk evaluator reads too, never
re-derived here. Figures come from ``driftless.calc``; the template formats, this
does no maths. Every queried collection is ORDER BY-sorted (the template sorts the
sprint history) for byte-identical regeneration."""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.assess.exposure import contingency_assessment
from driftless.calc import forecast as fc
from driftless.models import Milestone, Project
from driftless.report import engine, gather

SLUG = "forecast"
TITLE = "Forecast Report"


def _milestone_slips(session: Session, project: Project) -> list[dict[str, Any]]:
    """Each milestone with days slipped from its baseline date (``None`` if unbaselined).
    Batched via ``adapters.project_rows``; re-sorted to the exact (target_date, id)
    order the per-project ORDER BY used to give, so the bytes cannot move."""
    rows = sorted(
        adapters.project_rows(session, Milestone, project.id),
        key=lambda ms: (ms.target_date, ms.id),
    )
    return [
        {
            "name": row.name,
            "target": row.target_date,
            "baseline": row.baseline_date,
            "slip_days": gather.milestone_slip_days(row),
            "status": row.status,
        }
        for row in rows
    ]


def _sprint_history(project: Project, as_of: date) -> list[fc.Sprint]:
    """Completed sprints — those ended on or before ``as_of`` — as calc value objects.
    An in-flight or future sprint is not history (see ``driftless.calc.forecast``); keying
    "completed" off ``as_of`` keeps the report free of the wall clock. Length counts
    BOTH endpoints — 01-01 to 01-14 is a fourteen-day sprint, the same inclusive window
    ``calc.evm`` measures a baseline task over and the fortnight ``fc.Sprint`` defaults
    to; the exclusive difference ran every band date a day early per sprint needed. A
    same-day sprint (``end_date <= start_date``) is skipped: a single day carries no
    velocity information, and the API refuses to create one — this only guards a legacy
    row that predates that refusal. Sorted by ``(end_date, id)`` — the relationship
    carries no order_by, and database row order must never pick which sprint enters
    the velocity window."""
    return [
        fc.Sprint(
            s.name,
            ended_on=s.end_date,
            completed_points=s.completed_points,
            length_days=(s.end_date - s.start_date).days + 1,
        )
        for s in sorted(project.sprints, key=lambda s: (s.end_date, s.id))
        if s.end_date <= as_of and s.end_date > s.start_date
    ]


def _remaining_points(project: Project) -> float:
    """Story points still open: not-done, point-estimated tasks. Hours-estimated
    (predictive) work and unestimated tasks contribute nothing."""
    return sum(
        t.estimate
        for w in project.workstreams
        for t in w.tasks
        if t.estimate_unit == "points" and t.status != "done" and t.estimate is not None
    )


def render(session: Session, project: Project, as_of: date) -> str:
    """Render the Forecast document for ``project`` as of ``as_of``."""
    predictive = project.delivery_mode in ("predictive", "hybrid")
    agile = project.delivery_mode in ("agile", "hybrid")
    costs = gather.project_costs(session).get(project.id, [])
    snapshot = gather.project_evm(project, costs, as_of)
    history = _sprint_history(project, as_of) if agile else []
    band = fc.forecast_completion(history, _remaining_points(project), as_of) if history else None
    return engine.render(
        "forecast.md",
        {
            "title": TITLE,
            "project": project,
            "as_of": as_of,
            "mode": project.delivery_mode,
            "predictive": predictive,
            "s": snapshot,
            "milestones": _milestone_slips(session, project) if predictive else [],
            "band": band,
            "sprints": history,
            "c": contingency_assessment(session, project, snapshot, as_of),
        },
    )
