"""Scope knowledge-area evaluator: approved change requests not yet re-baselined.

Signal: change requests on the project that are ``approved`` but whose
``resulting_baseline_id`` is still null — scope the project has agreed to
change without the plan itself moving to reflect it. Amber at one or more
such requests, red at three or more (scope drift compounding rather than
being cleared as it lands). The recommended actions route the drift through
integrated change control and back into a re-baselined WBS. Pure and
as-of-parameterised — reads no wall clock.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.assess.model import Action, Assessment, RagStatus, Threat
from driftless.models import ChangeRequest, Project
from driftless.pmbok.state import threat_subject_ref

KIND = "scope"

_RED_UNBASELINED = 3


def evaluate(session: Session, project: Project, as_of: date) -> Assessment:
    """Assess the project's scope health as of ``as_of``."""
    crs = adapters.project_rows(session, ChangeRequest, project.id)
    unbaselined = [cr for cr in crs if cr.status == "approved" and cr.resulting_baseline_id is None]
    count = len(unbaselined)
    if count == 0:
        return Assessment(KIND, as_of, 0.0, "green")

    score = round(float(count), 4)
    ref = f"project:{project.id}"
    tid = threat_subject_ref(KIND, project.id)
    severity: RagStatus = "red" if count >= _RED_UNBASELINED else "amber"
    plural = "change" if count == 1 else "changes"
    threat = Threat(
        tid,
        KIND,
        severity,
        score,
        f"{count} approved {plural} to scope have not been re-baselined.",
        ref,
    )
    actions = (
        Action(
            f"scope:icc:{project.id}",
            "Route the change through integrated change control",
            "change_control_tools",
            "Confirm the change was board-reviewed before it is folded into the plan.",
            ref,
        ),
        Action(
            f"scope:rebaseline:{project.id}",
            "Re-baseline the WBS",
            "decomposition",
            "Decompose the approved change into the WBS and issue a new baseline version.",
            ref,
        ),
        Action(
            f"scope:review:{project.id}",
            "Run a scope review",
            "data_analysis",
            "Reconcile approved changes against the current baseline to catch any others adrift.",
            ref,
        ),
    )
    return Assessment(KIND, as_of, score, severity, (threat,), actions)
