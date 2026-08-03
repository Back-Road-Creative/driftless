"""The dated ChangeLog replay is the ONE source of truth for earned value.

``adapters.project_snapshot`` (the assessment path) replays task progress out of
the append-only ChangeLog, but ``snapshot_from`` called WITHOUT a progress series
— which is what ``gather.project_evm`` and every report/dashboard surface behind
it does — silently fell back to stamping today's ``Task.percent_complete`` at
``date.min``. One store, one project, one backdated as-of: ``cost-evm.md``
printed EV 800 / CPI 2.00 while the assessment printed CPI 0.50 and rated the
project red. These pin the two paths to one answer, and the replay itself
against two ways it could lie: a SQLite rowid reused after a delete handing a
brand-new task a dead task's history, and the per-session replay memo serving a
stale reading after a progress write in the same session. The prefetch scope is
pinned to fail CLOSED: a project outside the open scope raises instead of
answering every batched read with zero rows.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.assess import adapters
from driftless.db import Base, new_engine, new_session_factory
from driftless.db import changelog as audit
from driftless.report import gather

START, FINISH = date(2026, 1, 1), date(2026, 3, 31)  # a 90-day, 1000-cost plan line
ENTERED = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
STARTED = datetime(2026, 2, 5, 12, 0, tzinfo=UTC)
RAISED = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
BACKDATED = date(2026, 2, 15)  # after the 20% reading, before the 80% one


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
    """Commit with the change log's clock pinned to ``moment``."""
    monkeypatch.setattr(audit, "_utcnow", lambda: moment)
    db.commit()


def _seed(
    db: Session, monkeypatch: pytest.MonkeyPatch, moves: Sequence[tuple[datetime, int]]
) -> m.Project:
    """A one-task, one-line project whose percent_complete follows ``moves`` in time,
    with 400 of dated spend so CPI is defined at every as-of used below."""
    (created, start), *rest = moves
    portfolio = m.Portfolio(name="Content Brands", business=m.Business(name="BRC"))
    proj = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="GMS", project=proj)
    task = m.Task(name="GMS", workstream=stream, estimate_unit="hours", percent_complete=start)
    baseline = m.Baseline(project=proj, version=1, status="approved")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
    line.planned_start, line.planned_finish = START, FINISH
    db.add(line)
    db.add(m.CostEntry(project=proj, category="labour", incurred_on=START, amount=400.0))
    _commit_at(db, monkeypatch, created)
    for moment, percent in rest:
        task.percent_complete = percent
        _commit_at(db, monkeypatch, moment)
    return proj


def test_cost_report_ev_equals_assessment_ev_at_a_backdated_as_of(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-C1, in one assertion. The task went to 20% on 05 Feb and 80% on 01 Mar; asked
    about 15 Feb, the store can prove only 200 was earned. The report path used to
    answer with today's 80% — EV 800 / CPI 2.00 — while the assessment on the SAME
    store said CPI 0.50 and painted the project red."""
    project = _seed(logged, monkeypatch, [(ENTERED, 0), (STARTED, 20), (RAISED, 80)])
    assessment = adapters.project_snapshot(logged, project, BACKDATED)
    report = gather.project_evm(project, gather.project_costs(logged)[project.id], BACKDATED)
    assert (assessment.ev, assessment.cpi) == (200.0, 0.5)
    assert report == assessment, "the report path answered a different EV than the assessment"


def test_a_reused_rowid_does_not_inherit_a_dead_tasks_progress(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-C14. Delete the only task and SQLite hands its rowid to the next insert, so the
    dead task's logged 80% became the brand-new 0% task's history: EV 800 for work
    nobody has started. A logged delete must truncate the replayed readings."""
    project = _seed(logged, monkeypatch, [(ENTERED, 0), (STARTED, 20), (RAISED, 80)])
    stream = project.workstreams[0]
    task = stream.tasks[0]
    dead_id, baseline = task.id, project.baselines[0]
    logged.delete(baseline.lines[0])
    logged.delete(task)
    _commit_at(logged, monkeypatch, datetime(2026, 3, 2, 12, 0, tzinfo=UTC))
    reborn = m.Task(name="Reborn", workstream=stream, estimate_unit="hours", percent_complete=0)
    line = m.BaselineLine(baseline=baseline, task=reborn, planned_cost=1000.0)
    line.planned_start, line.planned_finish = START, FINISH
    logged.add(line)
    _commit_at(logged, monkeypatch, datetime(2026, 3, 3, 12, 0, tzinfo=UTC))
    assert reborn.id == dead_id, "premise: SQLite really did reuse the dead task's rowid"
    assert adapters.project_snapshot(logged, project, date(2026, 3, 15)).ev == 0.0


def test_a_progress_write_in_the_same_session_invalidates_the_replay_memo(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-C13. The replay is memoized per project on ``session.info``; without
    invalidation a session that reads, writes progress, then reads again is served
    the pre-write replay — the one cache in the module that could go stale."""
    project = _seed(logged, monkeypatch, [(ENTERED, 0), (STARTED, 20)])
    assert adapters.project_snapshot(logged, project, date(2026, 3, 15)).ev == 200.0
    project.workstreams[0].tasks[0].percent_complete = 80
    _commit_at(logged, monkeypatch, RAISED)
    assert adapters.project_snapshot(logged, project, date(2026, 3, 15)).ev == 800.0


def test_a_read_outside_the_open_prefetch_scope_raises_instead_of_answering_empty(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-C12. A batched read for a project the open scope never covered used to answer
    zero rows — real spend vanishing and every evaluator answering green. Fail closed."""
    inside = _seed(logged, monkeypatch, [(ENTERED, 50)])
    outside = m.Project(name="Elsewhere", portfolio=inside.portfolio, delivery_mode="predictive")
    logged.add(m.CostEntry(project=outside, category="labour", incurred_on=START, amount=250.0))
    _commit_at(logged, monkeypatch, RAISED)
    with adapters.prefetched(logged, [inside]):
        with pytest.raises(LookupError, match="prefetch"):
            adapters.project_rows(logged, m.CostEntry, outside.id)
