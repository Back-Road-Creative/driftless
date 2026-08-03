"""Which baseline is *the plan* — the one decision every earned-value figure rests on.

``adapters.snapshot_from`` is the single entry point for EVM in the whole product
(the Cost Report, the Weekly Status, the Forecast, the dashboard burn, the project
hub S-curve, the business S-curve and the persisted status percentage all reach it
through ``gather.project_evm``), so a wrong answer here is wrong everywhere at once.
It used to take the newest baseline of ANY status, which meant an unapproved draft
silently became the plan: BAC 4000 / CPI 5.00 / VAC +3200 printed in ``cost-evm.md``
beside a ``scope-baseline.md`` reading "Scope is unchanged since v1", whose approved
plan says BAC 1000 / CPI 1.25 / VAC 200. These pin the approved-only rule and the
empty state a project with no approved plan falls to.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.assess import adapters

AS_OF = date(2026, 3, 31)  # the shared conftest project's as-of and planned finish
JAN = date(2026, 1, 31)
BEFORE = date(2025, 6, 1)  # seven months before the plan's earliest planned start


def _rebaseline(db: Session, project: m.Project, version: int, status: str, cost: float) -> None:
    """A second plan version over the same task, at a different price."""
    task = project.workstreams[0].tasks[0]
    baseline = m.Baseline(project=project, version=version, status=status)
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=cost)
    line.planned_start, line.planned_finish = JAN, AS_OF
    db.add(line)
    db.commit()


def test_a_draft_rebaseline_moves_no_earned_value_figure(db: Session, project: m.Project) -> None:
    """The defect, in one assertion: draft v2 quadruples the budget, nobody approved
    it, and every figure must still answer against approved v1."""
    _rebaseline(db, project, version=2, status="draft", cost=4000.0)
    snap = adapters.project_snapshot(db, project, AS_OF)
    assert (snap.bac, snap.pv, snap.ev, snap.ac) == (1000.0, 1000.0, 500.0, 400.0)
    assert (snap.cpi, snap.spi, snap.eac, snap.vac) == (1.25, 0.5, 800.0, 200.0)


def test_the_plan_is_the_newest_approved_version_not_the_newest_row(
    db: Session, project: m.Project
) -> None:
    """Approved v1, draft v2, superseded v3: the plan is v1. A higher version number
    is a proposal or a retired plan until someone approves it."""
    _rebaseline(db, project, version=2, status="draft", cost=4000.0)
    _rebaseline(db, project, version=3, status="superseded", cost=9000.0)
    baseline = adapters.plan_baseline(project)
    assert baseline is not None and (baseline.version, baseline.status) == (1, "approved")


def test_a_second_approval_does_become_the_plan(db: Session, project: m.Project) -> None:
    """The rule is newest APPROVED, not oldest: an approved re-baseline is the plan."""
    _rebaseline(db, project, version=2, status="approved", cost=4000.0)
    assert adapters.project_snapshot(db, project, AS_OF).bac == 4000.0


def test_a_project_with_only_a_draft_reads_exactly_like_an_unbaselined_one(
    db: Session, project: m.Project
) -> None:
    """The empty state, pinned. ``plan_baseline`` answers ``None`` and the snapshot is
    the no-plan snapshot the product already defines — BAC/PV/EV 0, spend still real,
    every ratio built on the budget ``None`` so it renders ``n/a``. This is the Gantt
    page's "nothing to draw" and the Scope & Baseline document's "no versions", not a
    third convention, and emphatically not a quiet fall back to the draft's numbers.
    """
    unplanned = m.Project(name="Proposed", portfolio=project.portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="Proposed", project=unplanned)
    task = m.Task(name="Proposed", workstream=stream, estimate_unit="hours", percent_complete=50)
    draft = m.Baseline(project=unplanned, version=1, status="draft")
    line = m.BaselineLine(baseline=draft, task=task, planned_cost=4000.0)
    line.planned_start, line.planned_finish = JAN, AS_OF
    db.add(line)
    db.add(m.CostEntry(project=unplanned, category="labour", incurred_on=JAN, amount=400.0))

    bare = m.Project(name="Bare", portfolio=project.portfolio, delivery_mode="predictive")
    db.add(m.CostEntry(project=bare, category="labour", incurred_on=JAN, amount=400.0))
    db.commit()

    assert adapters.plan_baseline(unplanned) is None and adapters.plan_baseline(bare) is None
    snap = adapters.project_snapshot(db, unplanned, AS_OF)
    assert (snap.bac, snap.pv, snap.ev, snap.ac) == (0.0, 0.0, 0.0, 400.0)
    assert (snap.spi, snap.eac, snap.etc, snap.vac) == (None, None, None, None)
    assert snap == adapters.project_snapshot(db, bare, AS_OF)


def test_an_as_of_before_the_plan_began_claims_no_earned_value(
    db: Session, project: m.Project
) -> None:
    """The defect: ``percent_complete`` is undated, so stamping it at ``as_of`` served
    today's 50% as a measurement of any date asked for. The plan starts 2026-01-31;
    at 2025-06-01 nothing was even due to begin, so there is nothing to earn against.
    Hand-computed: no baseline answers, so BAC/PV/EV are 0; the one cost entry is
    dated 2026-01-31, so AC is 0 too; every ratio is undefined on a zero denominator.
    """
    snap = adapters.project_snapshot(db, project, BEFORE)
    assert (snap.bac, snap.pv, snap.ev, snap.ac) == (0.0, 0.0, 0.0, 0.0)
    assert (snap.cpi, snap.spi, snap.eac, snap.etc, snap.vac) == (None, None, None, None, None)


def test_the_refusal_still_answers_what_the_store_can_answer(
    db: Session, project: m.Project
) -> None:
    """Refusing earned value is not refusing the snapshot. Spend is dated, so AC
    answers every as-of: 250 incurred 2025-06-01 is still 250 at 2025-06-01, beside
    BAC/PV/EV 0. This is what keeps the swept PV/AC S-curves whole — they read those
    two lines and never EV. CPI is the empty state's own 0/AC, not a fresh convention.
    """
    db.add(m.CostEntry(project=project, category="labour", incurred_on=BEFORE, amount=250.0))
    db.commit()
    snap = adapters.project_snapshot(db, project, BEFORE)
    assert (snap.bac, snap.pv, snap.ev, snap.ac) == (0.0, 0.0, 0.0, 250.0)
    assert (snap.spi, snap.eac, snap.etc, snap.vac) == (None, None, None, None)


def test_the_plan_s_first_day_is_answerable(db: Session, project: m.Project) -> None:
    """The boundary is the plan's earliest ``planned_start``, inclusive: on 2026-01-31
    the plan has begun and every figure stands. Hand-computed PV: one line of 1000
    across a 60-day window (31 Jan - 31 Mar inclusive), one day elapsed -> 1000/60.
    """
    snap = adapters.project_snapshot(db, project, JAN)
    assert (snap.bac, snap.ev, snap.ac) == (1000.0, 500.0, 400.0)
    assert snap.pv == pytest.approx(1000.0 / 60.0)
