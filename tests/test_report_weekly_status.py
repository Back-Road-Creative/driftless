"""The Weekly Status document: the latest status reading, the project's earned-value
position (document == calc) and open risks ordered by exposure, rendered deterministically."""

from datetime import date

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.report import gather, render_document

AS_OF = date(2026, 3, 31)  # matches the conftest seed's baseline finish


def _seed(db: Session, project: m.Project) -> None:
    minor = m.Risk(project=project, description="minor risk", probability=0.2, impact=1000.0)
    major = m.Risk(project=project, description="major risk", probability=0.5, impact=20000.0)
    major.status = "mitigating"
    stale = m.Risk(project=project, description="stale risk", probability=0.9, impact=99999.0)
    stale.status = "closed"  # excluded from the open-risk list
    latest = m.StatusSnapshot(project=project, taken_on=date(2026, 3, 20), rag_status="amber")
    future = m.StatusSnapshot(project=project, taken_on=date(2026, 4, 10))  # after as_of — ignored
    # a second project's newer snapshot and bigger risk must never bleed into GMS's report
    rival = m.Project(name="Rival", portfolio=project.portfolio, delivery_mode="predictive")
    decoy_snap = m.StatusSnapshot(project=rival, taken_on=date(2026, 3, 25), rag_status="red")
    decoy_risk = m.Risk(project=rival, description="rival risk", probability=0.9, impact=90000.0)
    db.add_all([minor, major, stale, latest, future, rival, decoy_snap, decoy_risk])
    db.commit()


def test_weekly_status_is_deterministic(db: Session, project: m.Project) -> None:
    _seed(db, project)
    assert render_document("weekly-status", db, project, AS_OF) == render_document(
        "weekly-status", db, project, AS_OF
    )


def test_weekly_status_reports_no_variance_without_an_approved_plan(
    db: Session, project: m.Project
) -> None:
    """No approved plan means no basis for a variance, exactly as for CPI and SPI.

    Both variance cells used to print ``0.00`` — "exactly on budget, exactly on
    schedule" — for a project with no plan to be on, in the same table where the
    ratios correctly read ``n/a``.
    """
    unbaselined = m.Project(name="Pilot", portfolio=project.portfolio, delivery_mode="predictive")
    db.add(unbaselined)
    db.commit()

    costs = gather.project_costs(db).get(unbaselined.id, [])
    snap = gather.project_evm(unbaselined, costs, AS_OF)
    assert snap.bac == 0.0
    assert snap.cpi is None and snap.spi is None  # the convention the variances must match

    doc = render_document("weekly-status", db, unbaselined, AS_OF)
    assert "| Cost variance (CV) | n/a |" in doc
    assert "| Schedule variance (SV) | n/a |" in doc
    assert "0.00" not in doc  # nothing in this document may claim a figure it cannot know


def test_weekly_status_shows_latest_snapshot_evm_and_ordered_risks(
    db: Session, project: m.Project
) -> None:
    _seed(db, project)
    costs = gather.project_costs(db).get(project.id, [])
    snap = gather.project_evm(project, costs, AS_OF)
    doc = render_document("weekly-status", db, project, AS_OF)

    assert "GMS" in doc
    assert AS_OF.isoformat() in doc
    # the latest snapshot on or before as_of wins; the future one is ignored, and
    # the rival project's newer snapshot must not shadow GMS's own reading
    assert "2026-03-20" in doc
    assert "2026-04-10" not in doc
    assert "2026-03-25" not in doc
    assert "rival risk" not in doc, "another project's risks must not bleed in"
    # document == calc: CPI and the cost variance are calc's figures, formatted here
    assert snap.cpi is not None
    assert f"{snap.cpi:.2f}" in doc
    assert f"{snap.ev - snap.ac:.2f}" in doc
    # open/mitigating risks, biggest exposure first; the closed one is excluded
    assert doc.index("major risk") < doc.index("minor risk")
    assert "stale risk" not in doc
