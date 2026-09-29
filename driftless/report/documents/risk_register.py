"""The Risk Register / RAID log: one project's risks, issues and change requests
as Markdown. Every collection is fetched with an explicit ORDER BY so regeneration
is byte-identical; the template only formats, and ``Risk.exposure`` is a
``@hybrid_property`` (probability x impact), computed on read and never stored."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.models import ChangeRequest, Issue, Project, Risk, RiskResponse
from driftless.pmbok import mapping
from driftless.report import engine

SLUG = "risk-register"
TITLE = "Risk Register / RAID Log"


def render(session: Session, project: Project, as_of: date) -> str:
    """Render the RAID log for ``project`` as of ``as_of``."""
    pid = project.id
    risks = session.scalars(
        select(Risk).where(Risk.project_id == pid).order_by(Risk.exposure.desc(), Risk.id)
    ).all()
    # Batched via ``mapping.rows_for`` -- run once across the whole open
    # ``pmbok.state``/``mapping.prefetched`` scope (``_render_all``'s document loop)
    # instead of once per (document, project); the same scope
    # ``risk_facts.gather`` reads its own ``RiskResponse`` rows through, so the
    # two share one query and one cache entry.
    responses = sorted(mapping.rows_for(session, RiskResponse, pid), key=lambda r: r.id)
    issues = session.scalars(
        select(Issue).where(Issue.project_id == pid).order_by(Issue.raised_on, Issue.id)
    ).all()
    changes = session.scalars(
        select(ChangeRequest)
        .where(ChangeRequest.project_id == pid)
        .order_by(ChangeRequest.raised_on, ChangeRequest.id)
    ).all()
    return engine.render(
        "risk_register.md",
        {
            "title": TITLE,
            "project": project.name,
            "as_of": as_of,
            "risks": risks,
            "responses": responses,
            "issues": issues,
            "changes": changes,
        },
    )
