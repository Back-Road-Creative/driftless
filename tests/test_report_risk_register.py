"""The Risk Register / RAID log: risks ordered by exposure, issues and change
requests ordered by raised date, rendered byte-identically from the seeded rows."""

from datetime import date

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.report import render_document

AS_OF = date(2026, 3, 31)


def _seed(db: Session, project: m.Project) -> None:
    minor = m.Risk(project=project, description="minor risk", probability=0.1, impact=500.0)
    major = m.Risk(project=project, description="major risk", probability=0.4, impact=25000.0)
    major.status = "mitigating"
    issue = m.Issue(project=project, description="blocking issue", raised_on=date(2026, 2, 1))
    issue.risk = major  # RAID links the issue back to its source risk
    cr = m.ChangeRequest(project=project, description="scope change", raised_on=date(2026, 2, 15))
    owner = m.Person(name="Priya", department=None)
    response = m.RiskResponse(
        project=project,
        risk=major,
        strategy="mitigate",
        owner=owner,
        trigger="Vendor outage exceeds one day",
        planned_action="Fail over to the backup vendor",
        residual_probability=0.1,
        residual_impact=5000.0,
        cost_of_response=1000.0,
        schedule_days=3,
        status="planned",
        actor="pm",
        as_of=date(2026, 2, 20),
    )
    # a second project's RAID rows must never bleed into GMS's log
    rival = m.Project(name="Rival", portfolio=project.portfolio, delivery_mode="predictive")
    rival_risk = m.Risk(project=rival, description="rival risk", probability=0.9, impact=90000.0)
    rival_owner = m.Person(name="Rival Owner", department=None)
    decoys = [
        rival_risk,
        m.Issue(project=rival, description="rival issue", raised_on=date(2026, 2, 2)),
        m.ChangeRequest(project=rival, description="rival change", raised_on=date(2026, 2, 16)),
        m.RiskResponse(
            project=rival,
            risk=rival_risk,
            strategy="mitigate",
            owner=rival_owner,
            trigger="rival trigger",
            planned_action="rival action",
            residual_probability=0.1,
            residual_impact=1000.0,
            cost_of_response=0.0,
            schedule_days=0,
            status="planned",
            actor="pm",
            as_of=date(2026, 2, 20),
        ),
    ]
    db.add_all([minor, major, issue, cr, owner, response, rival, rival_owner, *decoys])
    db.commit()


def test_risk_register_is_deterministic(db: Session, project: m.Project) -> None:
    _seed(db, project)
    assert render_document("risk-register", db, project, AS_OF) == render_document(
        "risk-register", db, project, AS_OF
    )


def test_risk_register_lists_raid_rows_with_exposure_ordering(
    db: Session, project: m.Project
) -> None:
    _seed(db, project)
    doc = render_document("risk-register", db, project, AS_OF)

    assert "GMS" in doc
    assert AS_OF.isoformat() in doc
    # risks ordered by exposure desc: major (10000) before minor (50)
    assert doc.index("major risk") < doc.index("minor risk")
    # exposure is the hybrid probability*impact, formatted not recomputed
    assert f"{0.4 * 25000.0:.2f}" in doc  # 10000.00
    # the issue and change-request rows are present
    assert "blocking issue" in doc
    assert "scope change" in doc
    assert date(2026, 2, 1).isoformat() in doc  # the issue's raised_on
    assert "rival" not in doc, "another project's risks, issues and CRs must not bleed in"


def test_risk_register_lists_filed_responses(db: Session, project: m.Project) -> None:
    _seed(db, project)
    doc = render_document("risk-register", db, project, AS_OF)

    assert "## Risk responses" in doc
    assert "Priya" in doc and "Fail over to the backup vendor" in doc
    assert f"{0.1 * 5000.0:.2f}" in doc  # residual exposure, formatted not recomputed
    assert "Rival Owner" not in doc, "another project's responses must not bleed in"
