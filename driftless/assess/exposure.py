"""The one engine behind risk exposure, contingency held and the top risk.

The Forecast Report and the Risk evaluator (whose threat string the threat board, the
Assessment Report and the dashboard RAG all render) both import the entry point below,
so they cannot print different numbers. Rules, stated here and nowhere else: open risks
only, named by ``description``, since a closed risk cannot still cost the project; the
reserve held is the ``contingency`` ``BudgetLine`` capped at remaining budget, and no
line means none is held, not a default share. Reads route through
``adapters.project_rows``, so a whole-store walk batches. Reads no wall clock.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.calc import evm, forecast
from driftless.models import BudgetLine, Project, Risk
from driftless.models.records import OPEN_RISK_STATUSES


def open_register(session: Session, project: Project) -> list[forecast.Risk]:
    """The open risks, named by description, id-ordered so sums are stable."""
    return [
        forecast.Risk(row.description, row.probability, row.impact)
        for row in adapters.project_rows(session, Risk, project.id)
        if row.status in OPEN_RISK_STATUSES
    ]


def contingency_held(session: Session, project: Project, remaining_budget: float) -> float:
    """The reserve the budget records, capped at what is left to spend; 0.0 if none."""
    lines = adapters.project_rows(session, BudgetLine, project.id)
    held = next((line.planned_amount for line in lines if line.category == "contingency"), 0.0)
    return min(held, remaining_budget)


def contingency_assessment(
    session: Session, project: Project, snapshot: evm.EarnedValueSnapshot, as_of: date
) -> forecast.ContingencyAssessment:
    """Open-risk exposure weighed against the contingency held — for every surface."""
    remaining = adapters.remaining_budget(snapshot)
    held = contingency_held(session, project, remaining)
    assessed = forecast.assess_contingency(open_register(session, project), remaining, as_of, 0.0)
    # ``assess_contingency`` expresses contingency as remaining * rate; feeding
    # it ``held / remaining`` round-trips the reserve through a division
    # (486128.75 -> 486128.74999999994), so an exposure covered to the cent read
    # ``covered=False`` — red at score 0.0, which one sign-off then suppressed
    # forever. Carry the absolute reserve through instead: the figure the budget
    # records is the figure every surface judges and prints.
    return replace(assessed, contingency=held)
