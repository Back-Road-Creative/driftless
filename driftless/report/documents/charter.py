"""The Project Charter: the Initiating-phase snapshot — delivery mode, owning
portfolio and program, status note, stakeholder roster and key milestones. Field
listing only; deterministically sorted, so the same store regenerates byte-identically."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.models import Milestone, Project, Stakeholder
from driftless.report import engine

SLUG = "charter"
TITLE = "Project Charter"


def render(session: Session, project: Project, as_of: date) -> str:
    """Render the Charter for ``project`` as of ``as_of``."""
    stakeholders = session.scalars(
        select(Stakeholder)
        .where(Stakeholder.project_id == project.id)
        .order_by(Stakeholder.name, Stakeholder.id)
    ).all()
    # Batched via adapters.project_rows; re-sorted to the ORDER BY's exact order.
    milestones = sorted(
        adapters.project_rows(session, Milestone, project.id),
        key=lambda ms: (ms.target_date, ms.id),
    )
    return engine.render(
        "charter.md",
        {
            "title": TITLE,
            "project": project,
            "as_of": as_of,
            "stakeholders": stakeholders,
            "milestones": milestones,
        },
    )
