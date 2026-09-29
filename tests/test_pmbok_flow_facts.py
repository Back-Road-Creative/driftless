"""``BacklogItem`` carries no created_on/started_on/done_on columns; this replays
them from the ``ChangeLog`` — ``assess.adapters.progress_history``'s twin over
``status`` instead of ``percent_complete``. One rule, pinned here the same way
``test_assess_progress_history.py`` pins it for tasks: nothing dated after
``as_of`` counts, an item with no logged history falls back to its current
columns dated ``date.min``, and a logged delete truncates its row id's history."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.calc import flow
from driftless.db import Base, new_engine, new_session_factory
from driftless.db import changelog as audit
from driftless.pmbok import flow_facts

CREATED = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
STARTED = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
DONE = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)
AS_OF = date(2026, 1, 31)


@pytest.fixture
def logged(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'audited.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    audit.register_changelog(factory)
    with factory() as session:
        yield session


def _commit_at(db: Session, monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(audit, "_utcnow", lambda: moment)
    db.commit()


def _project(db: Session) -> m.Project:
    portfolio = m.Portfolio(name="Content Brands", business=m.Business(name="BRC"))
    proj = m.Project(name="GMS", portfolio=portfolio, delivery_mode="agile")
    db.add(proj)
    return proj


def test_created_started_done_are_replayed_from_the_changelog(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(logged)
    _commit_at(logged, monkeypatch, CREATED)
    item = m.BacklogItem(project=project, title="Ship it", story_points=5, status="proposed")
    logged.add(item)
    _commit_at(logged, monkeypatch, CREATED)
    item.status = "in_progress"
    _commit_at(logged, monkeypatch, STARTED)
    item.status = "done"
    _commit_at(logged, monkeypatch, DONE)

    (work_item,) = flow_facts.work_items_for_project(logged, project, AS_OF)
    assert work_item.created_on == CREATED.date()
    assert work_item.started_on == STARTED.date()
    assert work_item.done_on == DONE.date()
    assert work_item.points == 5.0


def test_a_transition_logged_after_as_of_does_not_count(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one property the dispatcher called out by name: a status change dated
    after ``as_of`` must be invisible to a report pinned at that earlier date —
    the same "what would this have read on that day" rule ``calc.flow`` documents."""
    project = _project(logged)
    _commit_at(logged, monkeypatch, CREATED)
    item = m.BacklogItem(project=project, title="Ship it", story_points=3, status="proposed")
    logged.add(item)
    _commit_at(logged, monkeypatch, CREATED)
    item.status = "in_progress"
    _commit_at(logged, monkeypatch, STARTED)
    item.status = "done"
    _commit_at(logged, monkeypatch, DONE)

    early = date(2026, 1, 10)  # after STARTED, before DONE
    (work_item,) = flow_facts.work_items_for_project(logged, project, early)
    assert work_item.started_on == STARTED.date()
    assert work_item.done_on is None, "a done_on logged after as_of must not appear"

    (still_open,) = flow_facts.work_items_for_project(logged, project, CREATED.date())
    assert still_open.started_on is None, "a started_on logged after as_of must not appear"


def test_a_deleted_items_history_does_not_leak_into_a_reborn_row(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(logged)
    _commit_at(logged, monkeypatch, CREATED)
    dead = m.BacklogItem(project=project, title="Dead", story_points=8, status="done")
    logged.add(dead)
    _commit_at(logged, monkeypatch, CREATED)
    dead.status = "done"
    _commit_at(logged, monkeypatch, STARTED)
    dead_id = dead.id
    logged.delete(dead)
    _commit_at(logged, monkeypatch, DONE)

    reborn = m.BacklogItem(project=project, title="Reborn", story_points=2, status="proposed")
    logged.add(reborn)
    _commit_at(logged, monkeypatch, DONE)
    assert reborn.id == dead_id, "sqlite reused the id — the scenario this test exists for"

    (work_item,) = flow_facts.work_items_for_project(logged, project, AS_OF)
    assert work_item.created_on == DONE.date(), (
        "the reborn row must not inherit the dead one's dates"
    )
    assert work_item.done_on is None


def test_an_item_with_no_logged_history_falls_back_to_its_current_status(db: Session) -> None:
    """A store built before ``register_changelog`` ran (or a fixture that never
    calls it) keeps reading what it always did: current status, dated
    ``date.min`` so it is visible at every as-of — the same fallback
    ``progress_history`` gives an undated task."""
    portfolio = m.Portfolio(name="Content Brands", business=m.Business(name="BRC"))
    project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="agile")
    db.add(m.BacklogItem(project=project, title="Untracked", story_points=1, status="in_progress"))
    db.commit()

    (work_item,) = flow_facts.work_items_for_project(db, project, AS_OF)
    assert work_item.created_on == date.min
    assert work_item.started_on == date.min
    assert work_item.done_on is None


def test_work_items_feed_wip_and_throughput(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(logged)
    _commit_at(logged, monkeypatch, CREATED)
    item = m.BacklogItem(project=project, title="Ship it", story_points=5, status="proposed")
    logged.add(item)
    _commit_at(logged, monkeypatch, CREATED)
    item.status = "in_progress"
    _commit_at(logged, monkeypatch, STARTED)

    items = flow_facts.work_items_for_project(logged, project, AS_OF)
    assert flow.wip(items, AS_OF) == 1
    assert flow.throughput(items, AS_OF - timedelta(days=6), AS_OF) == 0


def test_flow_leaf_metrics_reads_wip_throughput_and_median_cycle(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lean rollup-leaf reading: same wip/throughput ``flow_snapshot`` would
    report, without touching sprints, forecasts or burndown at all."""
    project = _project(logged)
    _commit_at(logged, monkeypatch, CREATED)
    item = m.BacklogItem(project=project, title="Ship it", story_points=5, status="proposed")
    logged.add(item)
    _commit_at(logged, monkeypatch, CREATED)
    item.status = "in_progress"
    _commit_at(logged, monkeypatch, STARTED)

    leaf = flow_facts.flow_leaf_metrics(logged, project, AS_OF)
    assert leaf.wip == 1
    assert leaf.throughput == 0
    assert leaf.median_cycle_days is None  # nothing has finished yet


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'plain.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


def test_sprint_history_and_remaining_points_match_the_old_forecast_helpers(db: Session) -> None:
    """These two functions moved out of ``report.documents.forecast`` unchanged;
    this pins their output against the calc value objects they must still build."""
    portfolio = m.Portfolio(name="Content Brands", business=m.Business(name="BRC"))
    project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="agile")
    stream = m.Workstream(name="Epic", project=project)
    db.add(m.Task(name="A", workstream=stream, estimate_unit="points", estimate=8.0, status="todo"))
    db.add(
        m.Sprint(
            project=project,
            name="S0",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 15),
            completed_points=10,
        )
    )
    db.commit()

    history = flow_facts.sprint_history(project, date(2026, 3, 31))
    assert len(history) == 1
    assert history[0].completed_points == 10
    assert flow_facts.remaining_points(project) == 8.0

    band = flow_facts.release_forecast(project, date(2026, 3, 31))
    assert band is not None
    assert band.remaining_points == 8.0


def test_release_forecast_is_none_with_no_sprint_history(db: Session) -> None:
    portfolio = m.Portfolio(name="Content Brands", business=m.Business(name="BRC"))
    project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="agile")
    db.add(project)
    db.commit()
    assert flow_facts.release_forecast(project, date(2026, 3, 31)) is None


ANCHOR = date(2026, 7, 1)  # an as-of anchor a store seeded today is rendered at
SEEDED_AT = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)  # ...and the wall clock it is seeded at
RAISED, STARTED_ON, FINISHED = date(2026, 6, 1), date(2026, 6, 10), date(2026, 6, 28)


def _dated_item(project: m.Project) -> m.BacklogItem:
    """One finished item whose whole history sits before ``ANCHOR``."""
    return m.BacklogItem(
        project=project,
        title="Shipped",
        story_points=5,
        status="done",
        created_on=RAISED,
        started_on=STARTED_ON,
        done_on=FINISHED,
    )


def test_stored_dates_carry_history_from_before_the_as_of_anchor(
    logged: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect these columns exist for. Every change here is LOGGED after
    ``ANCHOR`` — a store seeded today and rendered at an earlier anchor — so the
    ``ChangeLog`` replay sees nothing at that anchor and dates the item ``date.min``:
    its completion falls outside the trailing week and both duration medians vanish.
    The item's own dates are read instead, and they are the ones that are true."""
    project = _project(logged)
    logged.add(_dated_item(project))
    _commit_at(logged, monkeypatch, SEEDED_AT)

    snapshot = flow_facts.flow_snapshot(logged, project, ANCHOR)
    assert snapshot.throughput == 1, "a completion inside the trailing week must count"
    assert snapshot.cycle_time.median == 18.0
    assert snapshot.lead_time.median == 27.0
    assert flow_facts.flow_leaf_metrics(logged, project, ANCHOR).median_cycle_days == 18.0


def test_a_stored_date_after_the_as_of_anchor_does_not_count(db: Session) -> None:
    """Stored columns obey the same "what would this have read on that day" rule the
    replay does: a start or a finish dated later is invisible at the anchor."""
    db.add(_dated_item(project := _project(db)))
    db.commit()

    (mid,) = flow_facts.work_items_for_project(db, project, date(2026, 6, 15))
    assert (mid.created_on, mid.started_on, mid.done_on) == (RAISED, STARTED_ON, None)
    assert flow_facts.flow_snapshot(db, project, date(2026, 6, 15)).wip == 1
    (early,) = flow_facts.work_items_for_project(db, project, date(2026, 6, 5))
    assert early.started_on is None
