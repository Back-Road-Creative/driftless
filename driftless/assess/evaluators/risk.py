"""Risk knowledge-area evaluator: open-risk exposure against the contingency held.

Signal: the register's probability-weighted exposure versus the contingency held. Both
figures, and the top risk this names, come from ``driftless.assess.exposure`` — the one
engine the Forecast Report reads too, so the board and the document cannot disagree; this
module judges and derives nothing. Red when contingency does not cover exposure
(``covered`` is ``False``); amber when it is covered but exposure has already eaten past
half the contingency (the reserve is thinning); green otherwise, and when the register is
empty — no open risks, nothing to weigh.

Green too when no budget remains, which is the honest answer rather than a red: with
nothing left to spend, no reserve can be held and no share of one expressed, so an open
register has nothing to be weighed against. That covers a project nobody baselined and an
as-of before the plan began, where ``adapters.snapshot_from`` refuses earned value —
``bac == 0`` is the "nothing to assess" signal the cost evaluator already answers green
to, and a plan that does not exist promised no reserve to fall short of.

**The score is one unit whatever the reserve**: uncovered exposure as a share of the
budget left to spend. It used to be a share of *contingency*, floored against a $1
denominator so a zero reserve could not divide by zero — which silently made it raw
dollars, so a $600 uncovered exposure scored 600.0 and outranked a $45,000 one scoring
29.0 on the same ranked board. Guarding the division was right; letting the guard change
the unit was the bug. The floor is gone, the denominator is positive by the check above,
and no branch can change what the number means.

The recommended actions are the PMBOK risk tools & techniques for planning responses and
topping up reserve. Pure and as-of-parameterised — reads no wall clock.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.assess.exposure import contingency_assessment, open_register
from driftless.assess.model import Action, Assessment, RagStatus, Threat
from driftless.models import Project
from driftless.pmbok.state import threat_subject_ref

KIND = "risk"

_AMBER_COVERAGE = 0.5  # amber once exposure passes this share of contingency


def evaluate(session: Session, project: Project, as_of: date) -> Assessment:
    """Assess the project's risk exposure against its contingency as of ``as_of``."""
    if not open_register(session, project):
        return Assessment(KIND, as_of, 0.0, "green")

    snap = adapters.project_snapshot(session, project, as_of)
    assessment = contingency_assessment(session, project, snap, as_of)
    budget = assessment.remaining_budget
    if budget <= 0:
        return Assessment(KIND, as_of, 0.0, "green")

    red = not assessment.covered
    amber = not red and assessment.exposure > _AMBER_COVERAGE * assessment.contingency
    if not (red or amber):
        return Assessment(KIND, as_of, 0.0, "green")

    # Non-negative, monotonic in how far exposure has eaten the reserve, and one
    # unit for every project: the exposure the reserve fails to carry, as a share
    # of the budget left to spend. Uncovered, that is the shortfall; covered but
    # past the amber line, how far past the half-contingency mark exposure sits.
    # Either way 0 at the boundary back to green. ``budget`` is the denominator in
    # both branches and is positive above, so no floor is needed and no zero
    # reserve can quietly turn the score into dollars.
    if red:
        score = assessment.shortfall / budget
    else:
        score = max(0.0, assessment.exposure - _AMBER_COVERAGE * assessment.contingency) / budget
    score = round(score, 4)

    ref = f"project:{project.id}"
    tid = threat_subject_ref(KIND, project.id)
    severity: RagStatus = "red" if red else "amber"
    top_risk = assessment.top_risk if assessment.top_risk is not None else "n/a"
    threat = Threat(
        tid,
        KIND,
        severity,
        score,
        (
            f"Open-risk exposure {assessment.exposure:,.0f} against contingency "
            f"{assessment.contingency:,.0f} (top risk: {top_risk})."
        ),
        ref,
    )
    actions = (
        Action(
            f"risk:respond:{project.id}",
            "Plan responses for open threats",
            "strategies_for_threats",
            "Select avoid/mitigate/transfer/accept strategies for the largest open risks.",
            ref,
        ),
        Action(
            f"risk:reserve:{project.id}",
            "Run a reserve analysis",
            "reserve_analysis",
            "Weigh contingency held against total exposure and top up if short.",
            ref,
        ),
        Action(
            f"risk:contingent:{project.id}",
            "Prepare contingent response plans",
            "contingent_response_strategies",
            "Define trigger conditions and fallback plans for the top-ranked risks.",
            ref,
        ),
    )
    return Assessment(KIND, as_of, score, severity, (threat,), actions)
