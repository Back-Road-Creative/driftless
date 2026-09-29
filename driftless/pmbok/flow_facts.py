"""Flow-metric adapter: ``models`` rows -> ``calc.flow`` value objects, as-of aware.

``BacklogItem`` (``driftless.models.agile``) carries its own ``created_on`` /
``started_on`` / ``done_on``, and those columns are what this reads. The
alternative — the ``ChangeLog`` REPLAY kept below as the fallback for a row whose
``created_on`` is null, one written before the columns existed — dates an item by
the wall clock at the moment its row was WRITTEN, so a store seeded, imported or
restored into a fresh database today and read at an earlier anchor lost its flow
history entirely. The replay works the way ``assess.adapters.progress_history``
replays ``Task.percent_complete``: the insert is ``created_on``, the first logged
transition into ``in_progress`` is ``started_on``, the first into ``done`` is
``done_on``. Either way a date after the ``as_of`` asked about is not visible —
the same "what would this have read at the end of that day" rule ``calc.flow``
itself documents. An item with no logged history at all
(a fixture or legacy row that predates ``register_changelog``) falls back to
its CURRENT columns, dated ``date.min`` — the same "no history, no lie" fallback
``progress_history`` uses, so a store built before this adapter existed keeps
reading what it always did.

Batched through ``assess.adapters.project_grouped``/``project_rows`` — the same
prefetch scope every other evaluator read rides, so a store-wide walk (the
flow rollup) pays one query set for the lot rather than one per project.

**Sprint scoping is a known gap, stated rather than faked.** ``BacklogItem``
carries no ``sprint_id`` — there is no "this item belongs to this sprint"
column in the current schema — so burndown/burnup/cumulative-flow below are
drawn over the WHOLE project's backlog across the active sprint's calendar
window, not over that sprint's committed scope. That is the honest answer the
schema can give today; narrowing it to a true sprint backlog needs a column
this adapter does not invent.

``release_forecast`` reuses ``calc.forecast.forecast_completion`` over the same
sprint history and remaining-points reading ``report.documents.forecast`` used
to compute inline — moved here so the markdown Forecast Report and the flow
page/hub tile can never print two different bands for the same project.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import String, cast, select
from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.calc import flow
from driftless.calc import forecast as fc
from driftless.db.changelog import ChangeLog
from driftless.models import BacklogItem, Project, Sprint

_CHANGE_COLUMNS = (ChangeLog.row_id, ChangeLog.operation, ChangeLog.changed_at, ChangeLog.detail)
#: Ties a ``change_log`` row to the backlog item it describes, ``adapters._LOGS_A_TASK``'s
#: twin: ``row_id`` as text against the mapper's own table name.
_LOGS_A_BACKLOG_ITEM = (ChangeLog.table_name == BacklogItem.__tablename__) & (
    ChangeLog.row_id == cast(BacklogItem.id, String)
)
#: Every backlog-item ``change_log`` row joined to the project it belongs to, oldest
#: first — ``BacklogItem`` carries ``project_id`` directly, so this needs no extra
#: join the way ``adapters._TASK_CHANGES`` needs one through ``Workstream``.
_BACKLOG_ITEM_CHANGES = (
    select(BacklogItem.project_id, *_CHANGE_COLUMNS)
    .join(ChangeLog, _LOGS_A_BACKLOG_ITEM)
    .order_by(ChangeLog.changed_at, ChangeLog.id)
)
_CHANGES_KEY = "driftless.pmbok.flow_facts.backlog_item_changes"

#: The trailing window "throughput" reads over — a calendar week ending ``as_of``,
#: both ends inclusive, matching the plain-language "per week" figure the hub tile
#: and flow page print.
_THROUGHPUT_WINDOW_DAYS = 6


def _utc_date(moment: datetime) -> date:
    """The UTC calendar day ``moment`` falls on — ``adapters._utc_date``'s twin."""
    stamped = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return stamped.astimezone(UTC).date()


def _logged_status(operation: str, detail: str) -> str | None:
    """The ``status`` one ``change_log`` row records, or ``None`` for a row that
    moved no such column — ``adapters._logged_percent``'s twin over ``status``."""
    body: Any = json.loads(detail)
    if operation == "insert":
        value = body.get("new", {}).get("status")
    else:
        value = body.get("changed", {}).get("status", {}).get("new")
    return value if isinstance(value, str) else None


def _backlog_item_changes(session: Session, project_id: int) -> list[Any]:
    """This project's backlog-item ``change_log`` rows, oldest first — batched
    across an open ``adapters.prefetched`` scope like every other evaluator read."""

    def load(ids: Sequence[int]) -> Any:
        rows = session.execute(_BACKLOG_ITEM_CHANGES.where(BacklogItem.project_id.in_(ids)))
        return [(row[0], row[1:]) for row in rows]

    return adapters.project_grouped(session, _CHANGES_KEY, load, project_id)


@dataclass(frozen=True)
class _ReplayedDates:
    created_on: date
    started_on: date | None
    done_on: date | None


def _replay_dates(rows: Sequence[Any], as_of: date) -> dict[str, _ReplayedDates]:
    """Replay ``created_on``/``started_on``/``done_on`` per backlog-item row id,
    over ``rows`` already filtered to one project and ordered oldest-first.

    Nothing dated after ``as_of`` counts. A logged delete drops that row id's
    accumulated observations — the same tombstone rule ``progress_history``
    applies to a reused SQLite row id, so a reborn item never inherits a dead
    one's dates.
    """
    inserted_on: dict[str, date] = {}
    observed: dict[str, list[tuple[date, str]]] = {}
    for row_id, operation, changed_at, detail in rows:
        on = _utc_date(changed_at)
        if on > as_of:
            continue
        if operation == "delete":
            inserted_on.pop(row_id, None)
            observed.pop(row_id, None)
            continue
        if operation == "insert":
            inserted_on[row_id] = on
        status = _logged_status(operation, detail)
        if status is not None:
            observed.setdefault(row_id, []).append((on, status))
    dates: dict[str, _ReplayedDates] = {}
    for row_id, statuses in observed.items():
        created_on = inserted_on.get(row_id, date.min)
        started_on = next((on for on, status in statuses if status == "in_progress"), None)
        done_on = next((on for on, status in statuses if status == "done"), None)
        dates[row_id] = _ReplayedDates(created_on, started_on, done_on)
    return dates


def _seen(on: date | None, as_of: date) -> date | None:
    """``on``, unless dated after ``as_of`` — not visible on the day asked about."""
    return on if on is not None and on <= as_of else None


def work_items_for_project(session: Session, project: Project, as_of: date) -> list[flow.WorkItem]:
    """This project's backlog items as ``calc.flow.WorkItem``\\ s, as of ``as_of``:
    each item's own three dates, or — for a row whose ``created_on`` is null, written
    before those columns existed — the ``ChangeLog`` replay. An item with neither
    falls back to its current ``status``, dated ``date.min``, visible at every as-of
    — the same convention ``progress_history`` applies to an undated task."""
    rows = adapters.project_rows(session, BacklogItem, project.id)
    dated = _replay_dates(_backlog_item_changes(session, project.id), as_of)
    items = []
    for item in sorted(rows, key=lambda i: i.id):
        raised = item.created_on  # its own dates win; the replay is the legacy fallback
        known = (
            _ReplayedDates(raised, _seen(item.started_on, as_of), _seen(item.done_on, as_of))
            if raised is not None
            else dated.get(str(item.id))
        )
        if known is None:
            created_on = date.min
            started_on = date.min if item.status in ("in_progress", "done") else None
            done_on = date.min if item.status == "done" else None
        else:
            created_on, started_on, done_on = known.created_on, known.started_on, known.done_on
        items.append(
            flow.WorkItem(
                id=str(item.id),
                created_on=created_on,
                started_on=started_on,
                done_on=done_on,
                points=float(item.story_points or 0),
            )
        )
    return items


def sprint_history(project: Project, as_of: date) -> list[fc.Sprint]:
    """Completed sprints — ended on or before ``as_of`` — as ``calc.forecast``
    value objects. Moved here, unchanged, from ``report.documents.forecast`` so
    the markdown Forecast Report and the flow page read the same history; see
    that function's original docstring for why "completed" is keyed off
    ``as_of`` and why a same-day sprint is skipped."""
    return [
        fc.Sprint(
            s.name,
            ended_on=s.end_date,
            completed_points=s.completed_points,
            length_days=(s.end_date - s.start_date).days + 1,
        )
        for s in sorted(project.sprints, key=lambda s: (s.end_date, s.id))
        if s.end_date <= as_of and s.end_date > s.start_date
    ]


def remaining_points(project: Project) -> float:
    """Story points still open: not-done, point-estimated tasks. Moved here,
    unchanged, from ``report.documents.forecast``."""
    return sum(
        t.estimate
        for w in project.workstreams
        for t in w.tasks
        if t.estimate_unit == "points" and t.status != "done" and t.estimate is not None
    )


def release_forecast(project: Project, as_of: date) -> fc.CompletionBand | None:
    """The velocity completion band for ``project``, or ``None`` when there is no
    sprint history to forecast from — ``forecast_completion`` refuses an empty
    history rather than answer one, and this is the one place that refusal is
    turned into the "nothing to forecast yet" reading every caller wants."""
    history = sprint_history(project, as_of)
    if not history:
        return None
    return flow.release_forecast(history, remaining_points(project), as_of)


def _active_sprint(project: Project, as_of: date) -> Sprint | None:
    """The sprint whose window contains ``as_of``, or ``None``. Ties (more than
    one sprint claiming the same day, a data error the model does not forbid)
    break on id, so the choice is deterministic rather than row-order luck."""
    current = [s for s in project.sprints if s.start_date <= as_of <= s.end_date]
    return min(current, key=lambda s: s.id) if current else None


@dataclass(frozen=True)
class FlowSnapshot:
    """Every flow figure one project needs for its hub tile and its flow page,
    computed once so the two surfaces cannot disagree."""

    as_of: date
    wip: int
    throughput: int
    cycle_time: flow.DurationStats
    lead_time: flow.DurationStats
    forecast: fc.CompletionBand | None
    active_sprint: Sprint | None
    burndown: tuple[flow.BurndownPoint, ...]
    burnup: tuple[flow.BurnupPoint, ...]
    cumulative_flow: tuple[flow.CumulativeFlowPoint, ...]


@dataclass(frozen=True)
class FlowLeafMetrics:
    """The three flow figures ``calc.rollup.LeafMetrics`` carries — WIP, the
    trailing week's throughput, and the median cycle time — for one project.
    Lean on purpose: unlike :func:`flow_snapshot`, this never reads sprints,
    never computes a release forecast and never sweeps a burndown window, so a
    store-wide rollup walk pays only the two batched reads
    :func:`work_items_for_project` already makes, not a whole page's worth of
    figures per leaf."""

    wip: int
    throughput: int
    median_cycle_days: float | None


def flow_leaf_metrics(session: Session, project: Project, as_of: date) -> FlowLeafMetrics:
    """WIP, trailing-week throughput and median cycle time for one project's
    rollup leaf. Callers gate this on ``project.delivery_mode`` themselves
    (``report.gather``'s convention, matching :func:`sprint_history`'s agile
    branch) — a predictive project has no backlog items by construction, so
    calling this for one would spend a query proving nothing rather than
    reading ``delivery_mode`` for free off the row already in hand."""
    items = work_items_for_project(session, project, as_of)
    return FlowLeafMetrics(
        wip=flow.wip(items, as_of),
        throughput=flow.throughput(items, as_of - timedelta(days=_THROUGHPUT_WINDOW_DAYS), as_of),
        median_cycle_days=flow.cycle_time(items, as_of).median,
    )


def flow_snapshot(session: Session, project: Project, as_of: date) -> FlowSnapshot:
    """The one flow computation both the project hub tile and the flow page read."""
    items = work_items_for_project(session, project, as_of)
    active_sprint = _active_sprint(project, as_of)
    if active_sprint is not None:
        burndown = tuple(
            flow.burndown(items, active_sprint.start_date, active_sprint.end_date, as_of)
        )
        burnup = tuple(flow.burnup(items, active_sprint.start_date, active_sprint.end_date, as_of))
        cumulative = tuple(flow.cumulative_flow(items, active_sprint.start_date, as_of))
    else:
        burndown, burnup, cumulative = (), (), ()
    return FlowSnapshot(
        as_of=as_of,
        wip=flow.wip(items, as_of),
        throughput=flow.throughput(items, as_of - timedelta(days=_THROUGHPUT_WINDOW_DAYS), as_of),
        cycle_time=flow.cycle_time(items, as_of),
        lead_time=flow.lead_time(items, as_of),
        forecast=release_forecast(project, as_of),
        active_sprint=active_sprint,
        burndown=burndown,
        burnup=burnup,
        cumulative_flow=cumulative,
    )
