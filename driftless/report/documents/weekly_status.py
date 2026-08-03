"""The Weekly Status Report: the latest status reading, the project's earned-value
position and the top open risks — one project as Markdown. The template only
formats; the earned-value figures come from ``gather`` and the variances (which
the template must not compute) are derived here so the document cannot disagree
with calc. Every query carries an explicit ORDER BY so regeneration is byte-identical."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.models import Project, Risk, StatusSnapshot
from driftless.models.records import OPEN_RISK_STATUSES
from driftless.report import engine, gather

SLUG = "weekly-status"
TITLE = "Weekly Status Report"


def render(session: Session, project: Project, as_of: date) -> str:
    """Render the weekly status document for ``project`` as of ``as_of``.

    **A variance is a distance from an approved plan, so with no plan there is no
    distance.** ``bac == 0`` — never baselined, or an as-of before the plan began,
    the one "nothing to assess" signal every other surface already branches on —
    makes CV and SV ``None``, which the template's shared ``n(v)`` macro prints as
    ``n/a``: the same answer CPI, SPI and EAC give on that project, straight from
    calc's ``None`` discipline. The subtraction used to be unconditional, so the
    table stated one fact two ways — ``CPI n/a`` beside ``CV 0.00``, and a printed
    zero reads "exactly on budget, exactly on schedule" for a project that has
    neither. Not a wider guard than that: with a plan in hand, ``EV - AC`` before
    any spend lands is a real favourable variance, and only the *ratio* is
    undefined there.
    """
    snapshot = session.scalars(
        select(StatusSnapshot)
        .where(StatusSnapshot.project_id == project.id, StatusSnapshot.taken_on <= as_of)
        .order_by(StatusSnapshot.taken_on.desc(), StatusSnapshot.id.desc())
    ).first()
    costs = gather.project_costs(session).get(project.id, [])
    s = gather.project_evm(project, costs, as_of)
    risks = session.scalars(
        select(Risk)
        .where(Risk.project_id == project.id, Risk.status.in_(OPEN_RISK_STATUSES))
        .order_by(Risk.exposure.desc(), Risk.id)
    ).all()
    return engine.render(
        "weekly_status.md",
        {
            "title": TITLE,
            "project": project.name,
            "as_of": as_of,
            "snapshot": snapshot,
            "s": s,
            # cost/schedule variance — computed here, never in the template; None
            # (rendered n/a) with no approved plan to be a distance from.
            "cv": (s.ev - s.ac) if s.bac else None,
            "sv": (s.ev - s.pv) if s.bac else None,
            "risks": risks,
        },
    )
