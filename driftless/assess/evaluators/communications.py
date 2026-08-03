"""Communications knowledge-area evaluator: status-report recency vs cadence.

Signal: whether a status report exists at all, and if so whether the latest
snapshot is still fresh against the reporting cadence. Reuses the
``status_report`` resolver from the PMBOK mapping layer rather than
re-deriving cadence logic. Amber when reporting is stale (present but not
healthy) or missing entirely (not present); green when the latest report is
still fresh. The recommended actions are the PMBOK communications tools &
techniques. Pure and as-of-parameterised — reads no wall clock.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from driftless.assess.model import Action, Assessment, Threat
from driftless.models import Project
from driftless.pmbok import mapping
from driftless.pmbok.state import threat_subject_ref

KIND = "communications"


def evaluate(session: Session, project: Project, as_of: date) -> Assessment:
    """Assess the project's communications health as of ``as_of``."""
    status = mapping.resolve("status_report", project, session, as_of)
    if status.present and status.healthy:
        return Assessment(KIND, as_of, 0.0, "green")

    score = round(1.0 if not status.present else (0.5 if not status.healthy else 0.0), 4)
    ref = f"project:{project.id}"
    tid = threat_subject_ref(KIND, project.id)
    if not status.present:
        reason = "no status reporting at all"
    else:
        reason = "the latest status report is stale"
    threat = Threat(
        tid,
        KIND,
        "amber",
        score,
        f"Communications reporting is behind cadence: {reason} ({status.detail}).",
        ref,
    )
    actions = (
        Action(
            f"communications:report:{project.id}",
            "Issue a fresh status report",
            "communication_methods",
            "Publish a current status snapshot so stakeholders work from live data.",
            ref,
        ),
        Action(
            f"communications:channel:{project.id}",
            "Check the reporting channel and cadence",
            "communication_technology",
            "Confirm the distribution channel and tooling aren't what's blocking reports.",
            ref,
        ),
        Action(
            f"communications:review:{project.id}",
            "Hold a status review",
            "meetings",
            "Convene the team to reconcile what's actually happening against the last report.",
            ref,
        ),
    )
    return Assessment(KIND, as_of, score, "amber", (threat,), actions)
