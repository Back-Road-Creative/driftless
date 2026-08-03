"""The Schedule Report: one project's milestones with slip in days. Slip is
``(target_date - baseline_date).days`` when a baseline date exists, else undefined
("no baseline"), via the shared ``gather.milestone_slip_days`` — the same helper
the Forecast Report reads, so the two can't independently drift. This module's
own job is the template's formatting input; rows are ordered by ``target_date``
then id for byte-identical output."""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.models import MILESTONE_STATUSES, Milestone, Project
from driftless.report import engine, gather

SLUG = "schedule"
TITLE = "Schedule Report"


def render(session: Session, project: Project, as_of: date) -> str:
    """Render the Schedule document for ``project`` as of ``as_of``."""
    # Batched via adapters.project_rows; re-sorted to the ORDER BY's exact order.
    milestones = sorted(
        adapters.project_rows(session, Milestone, project.id),
        key=lambda ms: (ms.target_date, ms.id),
    )
    rows = [
        {
            "name": ms.name,
            "target": ms.target_date,
            "baseline": ms.baseline_date,
            "status": ms.status,
            "slip": gather.milestone_slip_days(ms),
        }
        for ms in milestones
    ]
    summary = {s: sum(ms.status == s for ms in milestones) for s in MILESTONE_STATUSES}
    context: dict[str, Any] = {
        "title": TITLE,
        "project": project.name,
        "as_of": as_of,
        "rows": rows,
        "summary": summary,
    }
    return engine.render("schedule.md", context)
