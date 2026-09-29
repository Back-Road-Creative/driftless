"""Procurement knowledge-area evaluator: contract disputes, lapsed agreements, and
contracted spend outrunning the budget.

Signal: every ``ProcurementAgreement`` on the project. DISPUTED fires when any
agreement carries ``status == "disputed"``; EXPIRED_ACTIVE fires when any
agreement is still ``"active"`` but its ``end_date`` has passed ``as_of``.
Separately, total contracted spend — the sum of ``amount`` across ``active``
and ``disputed`` agreements — is weighed against the project's total planned
budget (the sum of every ``BudgetLine.planned_amount``); OVER_BUDGET fires
when there is a budget to measure against and contracted spend exceeds it.
Red on a dispute or an over-budget contract book; amber on an expired-but-
still-active agreement with neither of those; green with no agreements, or
when none of the conditions fire. The recommended actions are the PMBOK
procurement tools & techniques. Pure and as-of-parameterised — reads no wall
clock.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.assess.model import Action, Assessment, RagStatus, Threat
from driftless.models import BudgetLine, Project, ProcurementAgreement
from driftless.pmbok.state import threat_subject_ref

KIND = "procurement"

_CONTRACTED_STATUSES = ("active", "disputed")

_DISPUTED_SCORE = 2.0
_OVER_BUDGET_SCORE = 1.0
_EXPIRED_ACTIVE_SCORE = 0.5


def evaluate(session: Session, project: Project, as_of: date) -> Assessment:
    """Assess the project's procurement health as of ``as_of``."""
    agreements = adapters.project_rows(session, ProcurementAgreement, project.id)
    if not agreements:
        return Assessment(KIND, as_of, 0.0, "green", coverage="not_applicable")

    disputed = [a for a in agreements if a.status == "disputed"]
    expired_active = [
        a
        for a in agreements
        if a.status == "active" and a.end_date is not None and a.end_date < as_of
    ]

    total_contracted = sum(a.amount for a in agreements if a.status in _CONTRACTED_STATUSES)
    total_budget = sum(
        line.planned_amount for line in adapters.project_rows(session, BudgetLine, project.id)
    )

    is_disputed = bool(disputed)
    is_expired_active = bool(expired_active)
    is_over_budget = total_budget > 0 and total_contracted > total_budget

    if not (is_disputed or is_expired_active or is_over_budget):
        return Assessment(KIND, as_of, 0.0, "green")

    score = round(
        (_DISPUTED_SCORE if is_disputed else 0.0)
        + (_OVER_BUDGET_SCORE if is_over_budget else 0.0)
        + (_EXPIRED_ACTIVE_SCORE if is_expired_active else 0.0),
        4,
    )
    red = is_disputed or is_over_budget
    severity: RagStatus = "red" if red else "amber"

    ref = f"project:{project.id}"
    tid = threat_subject_ref(KIND, project.id)
    conditions: list[str] = []
    if is_disputed:
        count = len(disputed)
        plural = "agreement" if count == 1 else "agreements"
        conditions.append(f"{count} disputed {plural}")
    if is_over_budget:
        conditions.append(
            f"contracted spend {total_contracted:,.0f} exceeds budget {total_budget:,.0f}"
        )
    if is_expired_active:
        count = len(expired_active)
        plural = "agreement" if count == 1 else "agreements"
        conditions.append(f"{count} active {plural} past end date")
    threat = Threat(
        tid,
        KIND,
        severity,
        score,
        f"Procurement at risk: {'; '.join(conditions)}.",
        ref,
    )
    actions = (
        Action(
            f"procurement:review:{project.id}",
            "Run a procurement performance review",
            "procurement_performance_reviews",
            "Check contracted vendors against delivery and spend commitments.",
            ref,
        ),
        Action(
            f"procurement:claims:{project.id}",
            "Open claims administration on disputed agreements",
            "claims_administration",
            "Work any disputed agreement toward resolution before it stalls delivery.",
            ref,
        ),
        Action(
            f"procurement:change_control:{project.id}",
            "Route contract changes through change control",
            "change_control_tools",
            "Re-scope or renew lapsed or over-committed agreements through change control.",
            ref,
        ),
    )
    return Assessment(KIND, as_of, score, severity, (threat,), actions)
