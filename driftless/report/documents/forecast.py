"""The Forecast Report: where a project is heading. A predictive project gets the
EVM completion forecast (EAC/ETC/VAC) and milestone slip against baseline; an agile
one gets the velocity-band completion forecast from its sprint history plus a seeded
Monte Carlo simulation (p50/p80/p90) over the same history — schedule forecasting,
not risk analysis; a hybrid one gets both. All share the risk exposure weighed
against the held contingency, from ``driftless.assess.exposure`` — the one engine
the Risk evaluator reads too, never re-derived here. Figures come from
``driftless.calc``; the template formats, this does no maths. Every queried
collection is ORDER BY-sorted (the template sorts the sprint history) for
byte-identical regeneration. The simulation's seed is the project id, never a wall
clock or unseeded random draw, so two renders of the same project are byte-identical.

Sprint history and remaining points are read through ``pmbok.flow_facts`` —
moved there so this document and the flow page/hub tile can never print two
different bands for the same project; see that module for the two functions'
original docstrings, unchanged here.
"""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.assess.exposure import contingency_assessment
from driftless.calc import forecast as fc
from driftless.models import Milestone, Project
from driftless.pmbok import flow_facts
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


def simulate_completion(
    history: list[fc.Sprint], remaining: float, as_of: date, seed: int
) -> fc.MonteCarloForecast:
    """Run the seeded Monte Carlo completion simulation for the "Simulated completion"
    block. The only call site for ``calc.forecast.monte_carlo_completion`` outside
    ``driftless/calc/`` — ``pmbok.proof_checks`` reruns the same simulation for its
    ``forecast`` proof check through this function rather than a second direct call,
    so the wedge claim that the schedule forecast is the sole Monte Carlo caller stays
    true (see ``tests/test_risk_report_names_what_renders.py``)."""
    return fc.monte_carlo_completion(history, remaining, as_of, seed=seed)


def render(session: Session, project: Project, as_of: date) -> str:
    """Render the Forecast document for ``project`` as of ``as_of``."""
    predictive = project.delivery_mode in ("predictive", "hybrid")
    agile = project.delivery_mode in ("agile", "hybrid")
    costs = gather.project_costs(session).get(project.id, [])
    snapshot = gather.project_evm(project, costs, as_of)
    history = flow_facts.sprint_history(project, as_of) if agile else []
    band = simulation = None
    if history:
        remaining = flow_facts.remaining_points(project)
        band = flow_facts.release_forecast(project, as_of)
        simulation = simulate_completion(history, remaining, as_of, seed=project.id)
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
            "simulation": simulation,
            "sprints": history,
            "c": contingency_assessment(session, project, snapshot, as_of),
        },
    )
