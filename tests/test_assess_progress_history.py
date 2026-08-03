"""Earned value read at the date asked for, replayed from the ChangeLog.

``Task.percent_complete`` is a bare current reading, and the EVM adapter used to hand
calc one report per task stamped with the as-of itself — so ``percent_complete_at``,
which correctly picks the newest reading on or before a date, always found today's
number whatever date it was handed. EV came out IDENTICAL at any two as-ofs inside the
plan window, which made every EV-derived trend arrow structurally unable to say "better"
or "worse". The append-only ``change_log`` already holds the series, so it is replayed
rather than invented and no new table is involved.

One rule decides every date — an undated reading answers every as-of, a dated change
answers from its own date on — and these pin its four faces: EV moves between two dates,
an update counts for the UTC date it was made on, a task reads as entered before its
first dated change, and a reading the log cannot date answers every as-of. The last two
keep existing stores whole: rows are typed up now and asked about last month.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.assess import adapters
from driftless.db import Base, ChangeLog, new_engine, new_session_factory
from driftless.db import changelog as audit

START, FINISH = date(2026, 1, 1), date(2026, 3, 31)  # a 90-day, 1000-cost plan line
ENTERED = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
STARTED = datetime(2026, 2, 5, 12, 0, tzinfo=UTC)
RAISED = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
TYPED_UP = datetime(2026, 7, 30, 14, 0, tzinfo=UTC)  # long after every as-of below


@pytest.fixture
def logged(tmp_path: Path) -> Iterator[Session]:
    """A store whose writes are audited, exactly as the API's and the wizard's are."""
    engine = new_engine(f"sqlite:///{tmp_path / 'audited.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    audit.register_changelog(factory)
    with factory() as session:
        yield session


def _commit_at(db: Session, monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    """Commit with the change log's clock pinned to ``moment`` — the listener still
    writes every row; only *when* it says they happened is under the test's control."""
    monkeypatch.setattr(audit, "_utcnow", lambda: moment)
    db.commit()


def _seed(
    db: Session, monkeypatch: pytest.MonkeyPatch, moves: Sequence[tuple[datetime, int]]
) -> m.Project:
    """A one-task, one-line project whose percent_complete follows ``moves`` in time."""
    (created, start), *rest = moves
    portfolio = m.Portfolio(name="Content Brands", business=m.Business(name="BRC"))
    proj = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="GMS", project=proj)
    task = m.Task(name="GMS", workstream=stream, estimate_unit="hours", percent_complete=start)
    baseline = m.Baseline(project=proj, version=1, status="approved")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
    line.planned_start, line.planned_finish = START, FINISH
    db.add(line)
    _commit_at(db, monkeypatch, created)
    for moment, percent in rest:
        task.percent_complete = percent
        _commit_at(db, monkeypatch, moment)
    return proj


def test_earned_value_differs_between_two_as_ofs_in_the_plan_window(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect, in one assertion. The task went to 20% on 05 Feb and to 80% on 01 Mar,
    so 15 Feb earned 200 of the line's 1000 and 15 Mar earned 800. Serving today's
    percentage for both dates made those two numbers equal."""
    project = _seed(logged, monkeypatch, [(ENTERED, 0), (STARTED, 20), (RAISED, 80)])
    early = adapters.project_snapshot(logged, project, date(2026, 2, 15))
    late = adapters.project_snapshot(logged, project, date(2026, 3, 15))
    assert (early.ev, late.ev) == (200.0, 800.0)
    assert early.ev != late.ev, "EV cannot move, so no EV-derived trend can move either"


def test_a_change_counts_for_the_utc_date_it_was_made_on(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The boundary: ``changed_at`` is an instant and ``as_of`` a calendar day, so a
    change belongs to every as-of on or after ITS OWN UTC date. A raise at 23:30 UTC on
    01 Mar is part of 01 Mar, one at 00:30 UTC on 02 Mar is not."""
    project = _seed(
        logged,
        monkeypatch,
        [
            (ENTERED, 0),
            (STARTED, 20),
            (datetime(2026, 3, 1, 23, 30, tzinfo=UTC), 80),
            (datetime(2026, 3, 2, 0, 30, tzinfo=UTC), 100),
        ],
    )
    days = (date(2026, 2, 28), date(2026, 3, 1), date(2026, 3, 2))
    evs = [adapters.project_snapshot(logged, project, d).ev for d in days]
    assert evs == [200.0, 800.0, 1000.0]


def test_a_date_before_the_first_dated_change_reads_the_task_as_entered(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plan starts 01 Jan; the task was entered at 0% and did not move until 05 Feb, so
    on 15 Jan it had earned nothing. Budget and planned value still stand: the plan HAD
    begun, it is the progress that had not."""
    project = _seed(logged, monkeypatch, [(ENTERED, 0), (STARTED, 20), (RAISED, 80)])
    snap = adapters.project_snapshot(logged, project, date(2026, 1, 15))
    assert (snap.bac, snap.ev) == (1000.0, 0.0)
    assert snap.pv > 0.0


def test_a_task_typed_up_after_the_as_of_still_answers_that_as_of(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One of the two cases that decide whether replay can ship. An insert is stamped when
    the ROW was created, not when the work reached that percentage, and every store is
    typed up now and asked about last month. Dating that reading at ``changed_at`` puts a
    task's only evidence AFTER every past as-of and collapses EV to 0 product-wide."""
    project = _seed(logged, monkeypatch, [(TYPED_UP, 20)])
    assert adapters.project_snapshot(logged, project, date(2026, 2, 15)).ev == 200.0


def test_a_task_with_no_logged_history_keeps_answering_with_its_current_reading(
    db: Session, project: m.Project
) -> None:
    """The other. A store written without ``register_changelog`` — this very fixture, and
    any install predating the listener — holds ZERO ``change_log`` rows, and a replay
    taking that literally would report every task 0%. A task the log cannot speak for
    falls back to its current reading: 50% of a 1000 line is 500 at every as-of."""
    assert db.scalar(select(func.count()).select_from(ChangeLog)) == 0
    for as_of in (date(2026, 3, 31), date(2026, 2, 28)):
        assert adapters.project_snapshot(db, project, as_of).ev == 500.0
