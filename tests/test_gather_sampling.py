"""The swept S-curves' sampling window and per-sample adaptation cost.

Two properties of the dashboard sweeps, pinned together because the same loop
carries both:

* **Byte-identity of the hoist.** ``gather.snapshot_sweep`` adapts a project's
  plan once per DISTINCT baseline the sampled span crosses and reuses it at
  every date that resolves to the same one; the sweep must stay equal to the
  canonical ``adapters.snapshot_from`` at EVERY date regime (before the plan
  window, at its edges, inside it, unbaselined, and across an approval landing
  mid-span), and the rendered curve/burn series must be byte-identical to the
  per-sample adapter construction they replaced. These pins are what license
  the hoist at all — and every fixture here left ``approved_at`` unset until
  the mid-span approvals below, which is why the pins could not fail for the
  one reason they most exist for.

* **Distinct sample dates.** ``gather.sample_dates`` over a window shorter
  than the sample count used to repeat dates — 12 samples over a 3-day span
  yielded 12 points on 4 distinct days — and ``home.html`` repeats the curve
  as one dated table row per point, so the accessible twin read the same date
  and figures three times over. Duplicates are collapsed at the window, once,
  rather than by each of its three consumers.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.assess import adapters
from driftless.report import gather
import test_web_home

# Assigned, not imported (the pattern test_web_scurve_table uses): these two are
# test fixtures that belong to ``test_web_home``, and reaching them through the
# module keeps one definition. The import order no longer matters either way --
# the app-mount cycle this comment used to warn about is gone.
_burn_series = test_web_home._burn_series
BURN_SAMPLES = test_web_home.BURN_SAMPLES

AS_OF = date(2026, 3, 31)
JAN = date(2026, 1, 31)


def _baselined(db: Session, name: str, cost: float, start: date, finish: date) -> m.Project:
    """One project with a single approved baselined task -- a sweep's raw input."""
    portfolio = m.Portfolio(name=name, business=m.Business(name=f"BRC {name}"))
    project = m.Project(name=name, portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name=name, project=project)
    task = m.Task(name=name, workstream=stream, estimate_unit="hours", percent_complete=25)
    baseline = m.Baseline(project=project, version=1, status="approved")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=cost)
    line.planned_start, line.planned_finish = start, finish
    db.add(line)
    return project


def _reapprove(db: Session, project: m.Project, cost: float, approved_at: datetime) -> None:
    """A second APPROVED version of ``project``'s one baselined task, same window,
    a DIFFERENT cost, approved partway through the sampled span. Every fixture in
    this file left ``approved_at`` unset, so it never mattered whether a pin's
    swept code picked the plan in force at each sample date (``adapters.snapshot_from``,
    since #184) or grabbed one plan for the whole sweep -- both read the single
    always-visible baseline the same way. Adding a second, dated approval is what
    makes a byte-identity pin against ``adapters.snapshot_from`` mean anything."""
    line = project.baselines[0].lines[0]
    baseline = m.Baseline(project=project, version=2, status="approved", approved_at=approved_at)
    second = m.BaselineLine(baseline=baseline, task=line.task, planned_cost=cost)
    second.planned_start, second.planned_finish = line.planned_start, line.planned_finish
    db.add(second)
    db.commit()


def test_sample_dates_collapses_a_window_shorter_than_the_sample_count() -> None:
    """12 samples over a 3-day span are 4 dates, one per calendar day — never
    the same date presented as several readings."""
    start = AS_OF - timedelta(days=3)
    assert gather.sample_dates([start], AS_OF, 12) == tuple(
        start + timedelta(days=i) for i in range(4)
    )


def test_sample_dates_degenerate_clamped_window_is_one_as_of_sample() -> None:
    """A start still in the future clamps the whole window onto ``as_of``; that
    is ONE reading, not twelve copies of it."""
    assert gather.sample_dates([date(2026, 5, 1)], AS_OF, 12) == (AS_OF,)


def test_sample_dates_long_window_still_yields_every_sample() -> None:
    """The fix only collapses genuine duplicates: a span longer than the sample
    count keeps its full, distinct, endpoint-inclusive sweep."""
    dates = gather.sample_dates([JAN], AS_OF, 12)
    assert len(dates) == 12 and len(set(dates)) == 12
    assert dates[0] == JAN and dates[-1] == AS_OF


def test_business_curve_carries_each_sampled_date_once(db: Session) -> None:
    """The C15 surface: a 3-day plan window sweeps to 4 dated points, so the
    S-curve's accessible table twin cannot repeat rows."""
    project = _baselined(db, "Short", 300.0, AS_OF - timedelta(days=3), AS_OF)
    db.add(m.CostEntry(project=project, category="labour", incurred_on=AS_OF, amount=120.0))
    db.commit()

    curve = gather.business_curve(gather.leaf_projects(db), gather.project_costs(db), AS_OF)

    dates = [point["date"] for point in curve["points"]]
    assert len(dates) == 4, "a 3-day window is 4 calendar days, so 4 points"
    assert dates == sorted(set(dates)), "each sampled date appears exactly once, in order"


def test_business_curve_is_byte_identical_to_the_per_sample_adapter(db: Session) -> None:
    """The P7 pin: the whole-business sweep must render exactly the series the
    canonical per-sample ``adapters.snapshot_from`` construction renders — same
    dates, same float sums in the same order, byte-for-byte."""
    a = _baselined(db, "A", 3100.0, date(2026, 1, 1), date(2026, 1, 31))
    db.add(m.CostEntry(project=a, category="labour", incurred_on=date(2026, 1, 1), amount=500.0))
    b = _baselined(db, "B", 3000.0, date(2026, 2, 1), date(2026, 3, 2))
    db.add(m.CostEntry(project=b, category="labour", incurred_on=date(2026, 2, 1), amount=200.0))
    db.commit()
    _reapprove(db, a, 3600.0, datetime(2026, 1, 20))  # a plan mid-sweep, cost actually moves
    projects = gather.leaf_projects(db)
    costs = gather.project_costs(db)

    plans = [pb for pb in (adapters.plan_baseline(p, AS_OF) for p in projects) if pb is not None]
    starts = [min(line.planned_start for line in pb.lines) for pb in plans if pb.lines]
    expected = [
        {
            "date": sample.isoformat(),
            "pv": round(
                sum(adapters.snapshot_from(p, costs.get(p.id, []), sample).pv for p in projects), 2
            ),
            "ac": round(
                sum(adapters.snapshot_from(p, costs.get(p.id, []), sample).ac for p in projects), 2
            ),
        }
        for sample in gather.sample_dates(starts, AS_OF, gather._BUSINESS_CURVE_SAMPLES)
    ]
    assert gather.business_curve(projects, costs, AS_OF) == {"points": expected}


def test_burn_series_is_byte_identical_to_the_per_sample_adapter(
    db: Session, project: m.Project
) -> None:
    """The same pin for the per-project burn sparkline (the other hoisted loop)."""
    _reapprove(db, project, 1800.0, datetime(2026, 2, 15))  # a plan mid-sweep, cost actually moves
    costs = gather.project_costs(db).get(project.id, [])
    baseline = adapters.plan_baseline(project, AS_OF)
    assert baseline is not None
    starts = [line.planned_start for line in baseline.lines]
    expected = [
        {"ac": round(adapters.snapshot_from(project, costs, sample).ac, 2)}
        for sample in gather.sample_dates(starts, AS_OF, BURN_SAMPLES)
    ]

    assert _burn_series(project, costs, AS_OF) == {
        "bac": round(adapters.snapshot_from(project, costs, AS_OF).bac, 2),
        "points": expected,
    }


def test_snapshot_sweep_matches_the_canonical_adapter_at_every_regime(
    db: Session, project: m.Project
) -> None:
    """The hoisted sweep and ``adapters.snapshot_from`` can never disagree: not
    before the plan window (the refused as-of), not at either edge, not inside
    it, not for a project with no approved plan at all, and not once a second
    baseline is approved partway through the sampled span."""
    _reapprove(db, project, 1800.0, datetime(2026, 2, 15))  # a plan mid-sweep, cost actually moves
    costs = gather.project_costs(db).get(project.id, [])
    at = gather.snapshot_sweep(project, costs)
    for as_of in (date(2025, 12, 31), JAN, date(2026, 2, 15), AS_OF):
        assert at(as_of) == adapters.snapshot_from(project, costs, as_of), as_of

    bare = m.Project(name="Bare", portfolio=project.portfolio, delivery_mode="predictive")
    db.add(bare)
    db.commit()
    assert gather.snapshot_sweep(bare, [])(AS_OF) == adapters.snapshot_from(bare, [], AS_OF)
