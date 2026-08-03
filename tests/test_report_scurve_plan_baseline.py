"""The business S-curve's sample window is set by the approved plan, like every figure on it.

``business_curve`` picked its x-axis from the newest baseline of ANY status, while every
number it plots comes from ``adapters.snapshot_from``, which is approved-only. The two
disagreed the moment somebody drafted a re-baseline: an unapproved v2 starting earlier
than the approved v1 stretched the axis back to dates the plan had not begun, and an
as-of before the plan's start earns nothing — so the dashboard curve filled with zero
samples that read as real reporting rather than as "not started yet".

The window and the numbers must answer to one approval rule, so this site reads
``adapters.plan_baseline`` like every other. ``None`` there means no approved plan, and
it is treated exactly as a project that was never baselined: it contributes no start,
never a fabricated one.
"""

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.db import Base, new_engine, new_session_factory
from driftless.report import gather

AS_OF = date(2026, 3, 31)
APPROVED_START = date(2026, 3, 1)
DRAFT_START = date(2026, 1, 1)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


def _project(name: str) -> m.Project:
    portfolio = m.Portfolio(name=name, business=m.Business(name=f"BRC {name}"))
    return m.Project(name=name, portfolio=portfolio, delivery_mode="predictive")


def _baseline(db: Session, project: m.Project, version: int, status: str, start: date) -> None:
    """One baselined task on ``project`` at ``version``/``status``, planned over 30 days."""
    label = f"{project.name} v{version}"
    stream = m.Workstream(name=label, project=project)
    task = m.Task(name=label, workstream=stream, estimate_unit="hours", percent_complete=0)
    baseline = m.Baseline(project=project, version=version, status=status)
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=3100.0)
    line.planned_start, line.planned_finish = start, start + timedelta(days=30)
    db.add(line)


def test_scurve_window_starts_at_the_approved_plan_not_an_unapproved_draft(db: Session) -> None:
    """Newest baseline is an unapproved draft starting two months before the approved
    plan, beside a project whose only baseline is a draft. The axis must start at the
    approved plan's start, so every sample sits inside a plan that has begun."""
    rebaselined = _project("Rebaselined")
    _baseline(db, rebaselined, 1, "approved", APPROVED_START)
    _baseline(db, rebaselined, 2, "draft", DRAFT_START)
    _baseline(db, _project("Proposed"), 1, "draft", date(2026, 2, 1))
    db.commit()

    curve = gather.business_curve(gather.leaf_projects(db), gather.project_costs(db), AS_OF)

    assert curve["points"][0]["date"] == APPROVED_START.isoformat(), (
        "the window starts at the approved plan; a draft re-baseline is a proposal, "
        "and a draft-only project has no plan to set an axis with"
    )
    assert curve["points"][-1]["date"] == AS_OF.isoformat()
    assert all(point["pv"] > 0 for point in curve["points"]), (
        "no sample may land before the plan began: those earn nothing, so the curve "
        "collapsed to zeros that read as reported spend rather than as not-yet-started"
    )


def test_a_project_whose_only_baseline_is_a_draft_reads_as_unbaselined(db: Session) -> None:
    """``plan_baseline`` returns ``None`` when nothing is approved. That is the empty
    state a never-baselined project already renders — not a window of zero samples."""
    _baseline(db, _project("Proposed"), 1, "draft", DRAFT_START)
    db.commit()

    curve = gather.business_curve(gather.leaf_projects(db), gather.project_costs(db), AS_OF)

    assert curve == {"points": []}, "no approved plan anywhere is the empty state"
