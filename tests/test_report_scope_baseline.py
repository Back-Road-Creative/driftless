"""The Scope & Baseline document compares the original plan (v1) with the current
one and lists the change requests that drove re-baselining. It must surface the
per-version planned-cost totals, the v1->v2 cost delta, and which CR produced
which baseline version; with a single baseline it reports scope unchanged."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.report import render_document

AS_OF = date(2026, 3, 31)


def _rebaseline(db: Session, project: m.Project) -> None:
    """Approve a change request that produces baseline v2, growing planned cost 1000 -> 1500."""
    task = db.scalars(select(m.Task)).one()  # the conftest project's single task
    v2 = m.Baseline(
        project=project, version=2, status="approved", approved_at=datetime(2026, 3, 15, 12, 0)
    )
    line = m.BaselineLine(baseline=v2, task=task, planned_cost=1500.0)
    line.planned_start, line.planned_finish = date(2026, 1, 31), date(2026, 4, 30)
    db.add(line)
    db.add(
        m.ChangeRequest(
            project=project,
            description="Extend scope",
            raised_on=date(2026, 3, 1),
            status="approved",
            resulting_baseline=v2,
        )
    )
    # a second project's change requests must never bleed into GMS's document
    rival = m.Project(name="Rival", portfolio=project.portfolio, delivery_mode="predictive")
    db.add(m.ChangeRequest(project=rival, description="Rival CR", raised_on=date(2026, 3, 2)))
    db.commit()


def test_the_same_inputs_render_byte_identically(db: Session, project: m.Project) -> None:
    _rebaseline(db, project)
    assert render_document("scope-baseline", db, project, AS_OF) == render_document(
        "scope-baseline", db, project, AS_OF
    )


def test_cost_growth_and_the_cr_that_drove_it(db: Session, project: m.Project) -> None:
    _rebaseline(db, project)
    doc = render_document("scope-baseline", db, project, AS_OF)

    assert "GMS" in doc
    assert AS_OF.isoformat() in doc
    assert "1000.00" in doc and "1500.00" in doc, "both baselines' planned-cost totals show"
    assert "500.00" in doc, "the v1->v2 planned-cost delta shows"
    assert "Extend scope" in doc and "v2" in doc, "the CR is linked to the version it produced"
    assert "Rival CR" not in doc, "another project's change requests must not bleed in"


def test_a_single_baseline_reports_scope_unchanged(db: Session, project: m.Project) -> None:
    doc = render_document("scope-baseline", db, project, AS_OF)
    assert "unchanged" in doc.lower()


def test_a_project_with_no_baseline_renders_a_placeholder(db: Session) -> None:
    """``report all`` must not die on a project that has never been baselined."""
    proj = m.Project(
        name="Empty Placeholder",
        portfolio=m.Portfolio(name="Content Brands", business=m.Business(name="BRC")),
        delivery_mode="predictive",
    )
    db.add(proj)
    db.commit()
    doc = render_document("scope-baseline", db, proj, AS_OF)
    assert doc.strip(), "a non-empty document is rendered"
    assert "no approved baseline" in doc.lower()


def test_a_draft_only_project_renders_the_placeholder_not_scope_unchanged(db: Session) -> None:
    """A DRAFT baseline is not yet a plan to compare against — the guard must gate
    on APPROVED status (the ``pmbok.mapping._approved_baseline`` convention), not
    merely on any baseline row existing, else a draft-only project wrongly reports
    scope unchanged instead of the "no approved baseline" placeholder."""
    proj = m.Project(
        name="Draft Only",
        portfolio=m.Portfolio(name="Content Brands", business=m.Business(name="BRC")),
        delivery_mode="predictive",
    )
    stream = m.Workstream(name="Draft", project=proj)
    task = m.Task(name="Draft task", workstream=stream, estimate_unit="hours")
    baseline = m.Baseline(project=proj, version=1, status="draft")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
    line.planned_start, line.planned_finish = date(2026, 1, 1), date(2026, 3, 31)
    db.add(line)
    db.commit()
    doc = render_document("scope-baseline", db, proj, AS_OF)
    assert "no approved baseline" in doc.lower()
    assert "unchanged" not in doc.lower()
