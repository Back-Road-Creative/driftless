"""The Schedule document lists a project's milestones with slip in days. Slip is
(target_date - baseline_date).days — positive when a milestone has moved out,
negative when it was pulled in early, and "no baseline" when none was set."""

from datetime import date

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.report import render_document

AS_OF = date(2026, 3, 31)


def _seed_milestones(db: Session, project: m.Project) -> None:
    db.add(
        m.Milestone(
            project=project,
            name="Late gate",
            target_date=date(2026, 4, 10),
            baseline_date=date(2026, 4, 1),
            status="at_risk",
        )
    )  # slip +9
    db.add(
        m.Milestone(
            project=project,
            name="Pulled in",
            target_date=date(2026, 2, 20),
            baseline_date=date(2026, 3, 1),
            status="met",
        )
    )  # slip -9 (early)
    db.add(
        m.Milestone(
            project=project,
            name="Unbaselined",
            target_date=date(2026, 5, 1),
            status="pending",
        )
    )  # no baseline
    # a second project's milestones must never bleed into GMS's schedule
    rival = m.Project(name="Rival", portfolio=project.portfolio, delivery_mode="predictive")
    db.add(
        m.Milestone(project=rival, name="Rival Gate", target_date=date(2026, 5, 1), status="missed")
    )
    db.commit()


def test_the_same_inputs_render_byte_identically(db: Session, project: m.Project) -> None:
    _seed_milestones(db, project)
    assert render_document("schedule", db, project, AS_OF) == render_document(
        "schedule", db, project, AS_OF
    )


def test_slip_is_the_signed_day_delta_and_the_summary_counts(
    db: Session, project: m.Project
) -> None:
    _seed_milestones(db, project)
    doc = render_document("schedule", db, project, AS_OF)

    assert "GMS" in doc
    assert AS_OF.isoformat() in doc
    assert "| 9 |" in doc, "a milestone that moved out shows a positive slip"
    assert "| -9 |" in doc, "a milestone pulled in early shows a negative slip"
    assert "no baseline" in doc, "a milestone with no baseline_date has undefined slip"
    assert "Met 1" in doc and "At risk 1" in doc and "Missed 0" in doc and "Pending 1" in doc
    assert "Rival Gate" not in doc, "another project's milestones must not bleed in"
