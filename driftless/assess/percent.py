"""The completion figure a status snapshot stamps, computed rather than typed."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.models import Project


def stamped_percent(db: Session, project: Project, as_of: date) -> int:
    """The project's percent complete at ``as_of``, computed from calc, never typed.

    Reads through :func:`driftless.assess.adapters.project_snapshot` — the
    session-holding EVM adapter whose ChangeLog replay dates each progress
    reading — so the number stamped onto a weekly snapshot is the figure that
    was true at the snapshot's OWN date. ``gather.project_evm`` holds no session,
    so it reads ``Task.percent_complete``, an undated *current* number: a
    snapshot backdated to February recorded today's completion, and the
    append-only series (no PATCH or DELETE exists for it) made that wrong figure
    permanent, plotted forever by the trend chart.
    """
    snap = adapters.project_snapshot(db, project, as_of)
    return round(snap.ev / snap.bac * 100) if snap.bac else 0
