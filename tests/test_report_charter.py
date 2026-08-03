"""The Project Charter lists the project's context, stakeholder roster and key
milestones, and regenerates byte-identically from the same store."""

from datetime import date

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.report import render_document

AS_OF = date(2026, 3, 31)


def _seed(db: Session, project: m.Project) -> None:
    db.add(m.Stakeholder(project=project, name="Ana", interest="high", influence="high"))
    db.add(m.Stakeholder(project=project, name="Bo", comms_cadence="weekly"))
    db.add(m.Milestone(project=project, name="Kickoff", target_date=date(2026, 2, 1)))
    db.add(m.Milestone(project=project, name="Launch", target_date=date(2026, 6, 1)))
    # a second project's roster and milestones must never bleed into GMS's charter
    rival = m.Project(name="Rival", portfolio=project.portfolio, delivery_mode="predictive")
    db.add(m.Stakeholder(project=rival, name="Rival Stakeholder"))
    db.add(m.Milestone(project=rival, name="Rival Gate", target_date=date(2026, 2, 1)))
    db.commit()


def test_charter_lists_stakeholders_and_milestones(db: Session, project: m.Project) -> None:
    _seed(db, project)
    doc = render_document("charter", db, project, AS_OF)

    assert "GMS" in doc
    assert AS_OF.isoformat() in doc
    assert project.delivery_mode in doc
    assert "Content Brands" in doc  # the owning portfolio
    for name in ("Ana", "Bo", "Kickoff", "Launch"):
        assert name in doc, f"charter must list {name}"
    assert "Rival" not in doc, "another project's stakeholders and milestones must not bleed in"


def test_charter_regenerates_byte_identically(db: Session, project: m.Project) -> None:
    _seed(db, project)
    assert render_document("charter", db, project, AS_OF) == render_document(
        "charter", db, project, AS_OF
    )
