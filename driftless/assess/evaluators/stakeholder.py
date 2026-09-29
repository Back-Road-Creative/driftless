"""Stakeholder knowledge-area evaluator: high-influence, low-interest engagement gaps.

Signal: stakeholders whose ``influence`` is ``"high"`` while their ``interest``
is ``"low"`` — the classic manage-closely quadrant of the power/interest grid,
a powerful player the project has let go disengaged. Green when the project
has no stakeholders registered at all (nothing to assess); amber at one or
more gap stakeholders, red at two or more. The recommended actions route the
gap back through the stakeholder engagement assessment matrix and the
communications plan. Pure and as-of-parameterised — reads no wall clock.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.assess.model import Action, Assessment, RagStatus, Threat
from driftless.models import Project, Stakeholder
from driftless.pmbok.state import threat_subject_ref

KIND = "stakeholder"

_RED_GAPS = 2


def evaluate(session: Session, project: Project, as_of: date) -> Assessment:
    """Assess the project's stakeholder health as of ``as_of``."""
    stakeholders = adapters.project_rows(session, Stakeholder, project.id)
    if not stakeholders:
        return Assessment(KIND, as_of, 0.0, "green", coverage="missing")

    gaps = [s for s in stakeholders if s.influence == "high" and s.interest == "low"]
    count = len(gaps)
    if count == 0:
        return Assessment(KIND, as_of, 0.0, "green")

    score = round(float(count), 4)
    ref = f"project:{project.id}"
    tid = threat_subject_ref(KIND, project.id)
    severity: RagStatus = "red" if count >= _RED_GAPS else "amber"
    plural = "stakeholder" if count == 1 else "stakeholders"
    threat = Threat(
        tid,
        KIND,
        severity,
        score,
        f"{count} high-influence, low-interest {plural} need managing closely.",
        ref,
    )
    actions = (
        Action(
            f"stakeholder:engage:{project.id}",
            "Reassess stakeholder engagement",
            "stakeholder_engagement_assessment_matrix",
            "Recheck current versus desired engagement for the disengaged power players.",
            ref,
        ),
        Action(
            f"stakeholder:comms:{project.id}",
            "Increase communication touchpoints",
            "communication_methods",
            "Raise the comms cadence and tailor the method to draw them back in.",
            ref,
        ),
        Action(
            f"stakeholder:analysis:{project.id}",
            "Re-run stakeholder analysis",
            "stakeholder_analysis",
            "Confirm the power/interest grid still reflects who can affect the project.",
            ref,
        ),
    )
    return Assessment(KIND, as_of, score, severity, (threat,), actions)
