"""Canonical DB → calc adapters the evaluators (and the report layer) share.

These turn stored rows into the frozen value objects ``driftless.calc`` consumes.
Placed in the assess layer, below report, precisely so both the assessment
engine and ``driftless.report.gather`` compute earned value the same way — one
implementation, no drift pair. Imports ``calc``, ``models``, ``db.changelog`` (the
replayed progress history) and ``pmbok.mapping`` (the batching scope below); reads no
wall clock — every entry takes ``as_of``, history dates come from stored ``changed_at``.

The eager-loading strategy lives here too, for the same reason. ``snapshot_from``
walks a project's plan baseline down to ``line.task.percent_complete`` — one
lazy query per baseline line under the default ``lazy="select"`` — and the two
hot read paths (the portfolio walk in ``driftless.report.gather`` and
``engine.top_threats``) each drive that walk over every project. ``eager_project``
returns the ``selectin`` loader options that collapse the Baseline → Line → Task
cascade and the milestone read into a fixed handful of round trips regardless of
project or task count. Both paths root their Project query on this one options
set so the strategy cannot drift between them, and it changes only *how many*
queries run, never *which rows* come back — so results stay byte-identical.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, TypeVar

from sqlalchemy import ColumnElement, ScalarResult, String, cast, event, select
from sqlalchemy.orm import Session, object_session, selectinload
from sqlalchemy.orm.strategy_options import _AbstractLoad

from driftless.calc import evm
from driftless.db.changelog import ChangeLog
from driftless.models import (
    Baseline,
    BaselineLine,
    CostEntry,
    Project,
    ScorecardMetricDefinition,
    Task,
    Workstream,
)
from driftless.pmbok import mapping

_M = TypeVar("_M")
_PREFETCH_KEY = "driftless.assess.adapters.prefetch"
_CHANGES_KEY = "driftless.assess.adapters.task_changes"
_HISTORY_KEY = "driftless.assess.adapters.progress_history"
_HISTORY_WATCH_KEY = "driftless.assess.adapters.progress_history_watch"
_ALL_CHANGES_KEY = "driftless.assess.adapters.task_changes_all"
_CHANGE_COLUMNS = (ChangeLog.row_id, ChangeLog.operation, ChangeLog.changed_at, ChangeLog.detail)
#: Ties a ``change_log`` row to the task it describes: ``row_id`` is the primary key as
#: text (``changelog._row_id``) and ``table_name`` the mapper's own table name.
_LOGS_A_TASK = (ChangeLog.table_name == Task.__tablename__) & (
    ChangeLog.row_id == cast(Task.id, String)
)
#: The open scope: the project ids it covers, plus the per-read row groups
#: :func:`project_grouped` fills in as each read is first made.
_PrefetchScope = tuple[list[int], dict[Any, dict[int, list[Any]]]]
_Load = Callable[[Sequence[int]], Iterable[tuple[int, Any]]]  # ids -> (project_id, row)


@contextmanager
def prefetched(session: Session, projects: Sequence[Project]) -> Iterator[None]:
    """Batch every evaluator's project-scoped read across ``projects``.

    The nine evaluators read their ``project_id``-scoped rows one project at a
    time, so a store-wide walk (``engine.top_threats``, ``gather.business_nodes``
    and the attention feed behind them) paid a query set per PROJECT — the cost
    that decides whether the dashboard works at commercial size. Inside this
    scope :func:`project_grouped` runs a read for EVERY project in one query the
    first time any project asks, and serves the rest from memory. There is no
    registry of reads to keep in step: a read that goes through it is batched by
    construction, and one that is never made costs nothing. The judging code is
    untouched, so per-project semantics are identical. Exit ``pop``s rather than
    ``del``s, so an accidentally nested scope degrades to the per-project queries
    instead of raising. A ``pmbok.mapping.prefetched`` scope opens alongside over
    the same projects — the communications evaluator resolves ``status_report``
    through the mapping layer's own cache, which this one cannot see.
    """
    session.info[_PREFETCH_KEY] = ([project.id for project in projects], {})
    try:
        with mapping.prefetched(session, projects):
            yield
    finally:
        session.info.pop(_PREFETCH_KEY, None)


def project_grouped(session: Session, key: Any, load: _Load, project_id: int) -> list[Any]:
    """One project's rows from ``load``, batched across an open :func:`prefetched`
    scope — run once for every project in it, else once for this project alone.

    ``key`` identifies the read in the scope's cache; rows group by the
    ``project_id`` ``load`` yields with each one, so a read whose rows carry no
    ``project_id`` column — the resource evaluator's tasks hang off
    ``Workstream`` — batches exactly like :func:`project_rows` does.

    A project the open scope never covered raises rather than answering. The
    batch query filtered on the scope's ids, so the cache genuinely does not
    know that project's rows — and serving the empty list instead is fail-open:
    real spend, risks and tasks silently vanish from every batched read and
    every evaluator answers green. There is no legitimate caller: every scope
    in the product is opened over exactly the projects it then walks.
    """
    scope: _PrefetchScope | None = session.info.get(_PREFETCH_KEY)
    if scope is None:
        return [row for _, row in load([project_id])]
    ids, cache = scope
    if key not in cache:
        grouped: dict[int, list[Any]] = {pid: [] for pid in ids}
        for pid, row in load(ids):
            grouped[pid].append(row)
        cache[key] = grouped
    if project_id not in cache[key]:
        raise LookupError(
            f"project {project_id} is outside the open prefetch scope: its rows were "
            "never batched, so answering would silently claim it has none"
        )
    return list(cache[key][project_id])


def project_rows(session: Session, model: type[_M], project_id: int) -> list[_M]:
    """``model``'s rows for one project, id order — batched across the whole
    :func:`prefetched` scope when one is open, else one per-project SELECT."""
    table: Any = model

    def load(ids: Sequence[int]) -> Iterable[tuple[int, Any]]:
        rows: ScalarResult[Any] = session.scalars(
            select(table).where(table.project_id.in_(ids)).order_by(table.id)
        )
        return ((row.project_id, row) for row in rows)

    return project_grouped(session, model, load, project_id)


def eager_project() -> tuple[_AbstractLoad, ...]:
    """``selectin`` loader options for a Project's EVM hierarchy and milestones.

    Rooted at ``Project``: applied directly to a ``select(Project)`` (as in
    ``engine.top_threats``) or nested under ``selectinload(Portfolio.projects)``
    (as in ``gather.portfolio_nodes``). Eager-loads ``baselines → lines → task``
    — the cascade ``snapshot_from`` reads — and ``milestones``, so the hierarchy
    resolves in a constant number of statements instead of one per row.
    """
    return (
        selectinload(Project.baselines)
        .selectinload(Baseline.lines)
        .selectinload(BaselineLine.task),
        selectinload(Project.milestones),
    )


def plan_baseline(project: Project, as_of: date | None = None) -> Baseline | None:
    """The baseline that IS ``project``'s plan: its newest *approved* version whose
    approval an as-of of ``as_of`` can already see, or ``None`` when nobody had
    approved one by then.

    THE one definition, imported by every surface that needs a plan, because the
    alternative shipped: this module took the newest baseline of any status, so an
    unapproved draft re-baseline silently rewrote every earned-value figure in the
    product — ``cost-evm.md`` printing BAC 4000 / CPI 5.00 / VAC +3200 beside a
    ``scope-baseline.md`` reading "Scope is unchanged since v1", whose approved plan
    says BAC 1000 / CPI 1.25 / VAC 200. A draft is a proposal; it becomes the plan
    when someone approves it, which is the rule the Gantt page, the capacity heatmap,
    the PMBOK artifact map and the Scope & Baseline document already applied.

    ``as_of`` narrows the approved candidates to those a rendering at that date
    could have known about: a version whose ``approved_at`` falls after ``as_of`` is
    invisible, because the second defect shipped alongside the first — a baseline
    approved in July silently became the plan for a report already rendered as of
    March, so re-rendering that same March as-of after the July approval printed
    different numbers for a date that had already happened, exactly what
    ``docs/temporal-model.md`` forbids. A row with ``approved_at is None`` stays
    visible at every ``as_of`` instead of being dropped: a missing approval instant
    is not evidence the approval happened after any particular date, and treating
    silence as "must be recent" would erase plans that predate the column.

    ``as_of=None`` is a second, deliberately permissive reading: newest approved,
    full stop — the LIVE view the re-baseline write guard needs, since refusing a
    second approved baseline (``web.wizard_pages.wizard_apply``) must see every approval
    right now, or a stale ``as_of`` could sneak one past the 409. Not a convenience
    default for a report surface: every such caller passes its own ``as_of``, and
    ``tests/test_baseline_selection.py`` names every present-day exception so a new
    one cannot join silently. ``None`` from either reading means no plan is visible,
    treated like a project never baselined — BAC 0, never a fall back to a draft.
    ``(project_id, version)`` is uniquely constrained, so the ``max`` is total. Pure:
    reads the eager-loaded collection :func:`eager_project` fetches and the plain
    mapped ``approved_at`` column, firing no query.
    """
    approved = [b for b in project.baselines if b.status == "approved"]
    if as_of is not None:
        approved = [b for b in approved if b.approved_at is None or b.approved_at.date() <= as_of]
    return max(approved, key=lambda b: b.version) if approved else None


def metric_definition_as_of(
    definitions: Sequence[ScorecardMetricDefinition], as_of: date | None = None
) -> ScorecardMetricDefinition | None:
    """The version of ONE logical metric — the rows in ``definitions`` sharing one
    ``(objective_id, name)`` — in force as of ``as_of``. :func:`plan_baseline`'s
    structural twin: ``as_of=None`` is the same permissive LIVE reading, a start of
    ``METRIC_ALWAYS`` answers every date as an unset ``approved_at`` does, and
    ``id`` breaks a same-day tie."""
    eligible = [d for d in definitions if as_of is None or d.effective_from <= as_of]
    return max(eligible, key=lambda d: (d.effective_from, d.id)) if eligible else None


def approved_as_of(as_of: date) -> ColumnElement[bool]:
    """The SQL-level twin of :func:`plan_baseline`'s date gate, for the two surfaces that
    pick a baseline in a QUERY rather than over an already-loaded ``Project`` — the Gantt
    page and the capacity heatmap. A row with no recorded ``approved_at`` stays visible at
    every ``as_of`` — the SAME null policy as :func:`plan_baseline`, never a second one
    invented for SQL: a missing approval instant is not evidence the approval happened
    after any particular date. Callers still write ``Baseline.status == "approved"``
    themselves, so "approved" stays a literal in their own scope, where
    ``tests/test_baseline_selection.py`` reads it off the syntax tree.

    Expressed as a HALF-OPEN instant compare — everything strictly before midnight ending
    ``as_of`` — which is exactly :func:`plan_baseline`'s ``approved_at.date() <= as_of``
    for the naive timestamps this column stores, so an approval at 09:00 on ``as_of``
    itself still counts. Deliberately not a day-truncating SQL function over the column:
    the suite runs entirely on SQLite while a deployment runs Postgres, and the one CI job
    that speaks Postgres runs ``tests/test_migrations.py`` and no application query — so a
    function that exists in one dialect and not the other would be green here and fail only
    in production. A plain comparison is the same answer in every dialect, and leaves the
    column bare so an index on it can still be used.
    """
    midnight_after = datetime.combine(as_of + timedelta(days=1), time())
    return (Baseline.approved_at.is_(None)) | (Baseline.approved_at < midnight_after)


def _utc_date(moment: datetime) -> date:
    """The UTC calendar day ``moment`` falls on. SQLite hands the offset back stripped,
    so a naive value is read as the UTC it was written as, never as local time."""
    stamped = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return stamped.astimezone(UTC).date()


def _logged_percent(operation: str, detail: str) -> int | None:
    """The ``percent_complete`` one ``change_log`` row records, or ``None`` for a row that
    moved no such column: an insert logs every column, an update only the ones that
    changed, and a delete describes a row no baseline line can still point at."""
    body: Any = json.loads(detail)
    if operation == "insert":
        value = body.get("new", {}).get("percent_complete")
    else:
        value = body.get("changed", {}).get("percent_complete", {}).get("new")
    return value if isinstance(value, int) else None


#: Every task ``change_log`` row joined to the project it belongs to, oldest first.
#: Columns, never entities: an instance per row would drag the audit trail into the
#: identity map for a read that wants four values.
_TASK_CHANGES = (
    select(Workstream.project_id, *_CHANGE_COLUMNS)
    .join(Task, Task.workstream_id == Workstream.id)
    .join(ChangeLog, _LOGS_A_TASK)
    .order_by(ChangeLog.changed_at, ChangeLog.id)
)


def _task_changes(session: Session, project_id: int) -> list[Any]:
    """This project's task ``change_log`` rows, oldest first — never one query per
    project. Inside a :func:`prefetched` scope the read batches across the scope's
    projects like every other evaluator read; outside one it loads the WHOLE store's
    task changes once per session and memoizes (``gather.project_costs``'s idiom),
    because the un-scoped callers are store-wide walks — the Department report
    renders every department's project list — and a per-project query there is the
    exact N+1 the statement ceilings exist to catch. The memo is dropped by
    :func:`_forget_history` whenever the session flushes or rolls back."""
    if session.info.get(_PREFETCH_KEY) is not None:

        def load(ids: Sequence[int]) -> Iterable[tuple[int, Any]]:
            rows = session.execute(_TASK_CHANGES.where(Workstream.project_id.in_(ids)))
            return [(row[0], row[1:]) for row in rows]

        return project_grouped(session, _CHANGES_KEY, load, project_id)
    cache: dict[int, list[Any]] | None = session.info.get(_ALL_CHANGES_KEY)
    if cache is None:
        cache = {}
        for row in session.execute(_TASK_CHANGES):
            cache.setdefault(row[0], []).append(row[1:])
        session.info[_ALL_CHANGES_KEY] = cache
    return cache.get(project_id, [])


def _forget_history(session: Session, *_: object) -> None:
    """Drop the replay memos: the flush (or rollback) this fires on may have moved
    the very task rows the memoized replay was computed from."""
    session.info.pop(_HISTORY_KEY, None)
    session.info.pop(_ALL_CHANGES_KEY, None)


def progress_history(
    session: Session, project: Project, as_of: date | None = None
) -> list[evm.ProgressReport]:
    """The dated progress readings ``project``'s plan tasks actually followed, as of
    ``as_of`` — replayed over :func:`plan_baseline`'s lines at that date, so the task
    ids returned can change with which plan version ``as_of`` sees.

    ``Task.percent_complete`` is one undated *current* number, so stamping it with the
    as-of being asked about made today's reading the measurement of every date: EV came
    out identical at any two as-ofs inside the plan window, and a trend arrow comparing
    them could only ever read "flat". The series was never missing — the append-only
    ``change_log`` has held it all along — so it is replayed rather than invented, and
    there is no new table or column to migrate to.

    ONE rule decides every date: **an undated reading answers every as-of; a dated change
    answers from its own date on.** Its three faces, each pinned by
    ``tests/test_assess_progress_history.py``:

    * **UTC.** ``changed_at`` is an instant, ``as_of`` a calendar day, so an update
      counts for as-of D when its UTC date is on or before D — a raise at 23:30 UTC on
      the 1st belongs to the 1st, one at 00:30 UTC on the 2nd does not. Same-day updates
      collapse to the last, that day's closing reading. Before its first dated change a
      task reads the percentage it was entered with — 0 for one created the ordinary way.
    * **An insert is undated.** It records when the ROW was created, never when the work
      reached that percentage, and those are routinely months apart: a store is typed up
      now and asked about last month (the demo seed posts a portfolio today against an
      anchor months back). Dating it at ``changed_at`` puts a task's only evidence AFTER
      every past as-of and collapses earned value to 0 across the product — measured, on
      the threat board's own fixture. So the creation reading is dated ``date.min``, and
      only an update, a value that provably MOVED on a day, carries a date.
    * **No logged reading at all** falls back to the task's current ``percent_complete``,
      dated ``date.min`` by the same rule — the behaviour that preceded any history, so a
      store written through a session ``register_changelog`` was never called on (every
      install predating the listener, and the shared test fixtures) keeps reading what it
      always did. It keys on having no logged *percentage* rather than no rows, so a task
      whose only logged change was its name is covered too.

    **A logged delete truncates its row's replayed readings.** SQLite reuses a deleted
    row's id, and the log keys on that id as text — so without the truncation a
    brand-new 0% task created after a delete answered with the DEAD task's history,
    earning value for work nobody has started. The tombstone is in the same ordered
    log, so everything logged before it is the dead task's and is dropped; the reborn
    task's own rows follow it and replay from scratch.

    Memoized on the session per ``(project, the baseline replayed against)`` and
    batched across an open :func:`prefetched` scope, so a store-wide walk pays one
    query for the lot, not one per snapshot. The project alone used to be key
    enough; once :func:`plan_baseline` became date-aware, two as-ofs in one session
    would have shared one replay — a wrong answer, not a slow one. The PLAN keys
    it, not ``as_of``: the date reaches this replay only by choosing which lines it
    runs over, so two dates picking one version have identical output and a date
    key would pay twice — as the dashboard would, reading every project at the
    as-of and again a week back for its trend. Invalidated on the session's own
    flushes and rollbacks — listeners registered once per session the first time it
    memoizes — so a session that writes progress and reads again is never served
    the pre-write replay, and a read-only walk keeps it across every scope free."""
    baseline = plan_baseline(project, as_of)
    if baseline is None:
        return []
    cache: dict[tuple[int, int], list[evm.ProgressReport]] = session.info.setdefault(
        _HISTORY_KEY, {}
    )
    key = (project.id, baseline.id)
    if key in cache:
        return cache[key]
    if not session.info.get(_HISTORY_WATCH_KEY):
        event.listen(session, "after_flush", _forget_history)
        event.listen(session, "after_soft_rollback", _forget_history)
        session.info[_HISTORY_WATCH_KEY] = True
    readings: dict[str, dict[date, int]] = {}
    for row_id, operation, changed_at, detail in _task_changes(session, project.id):
        if operation == "delete":
            readings.pop(row_id, None)  # a dead task's history must not outlive it
            continue
        percent = _logged_percent(operation, detail)
        if percent is not None:
            on = date.min if operation == "insert" else _utc_date(changed_at)
            readings.setdefault(row_id, {})[on] = percent
    reports: list[evm.ProgressReport] = []
    for line in baseline.lines:
        dated = readings.get(str(line.task_id)) or {date.min: line.task.percent_complete}
        reports.extend(
            evm.ProgressReport(str(line.task_id), on, percent / 100)
            for on, percent in sorted(dated.items())
        )
    cache[key] = reports
    return reports


def snapshot_from(
    project: Project,
    costs: Sequence[CostEntry],
    as_of: date,
    progress: Sequence[evm.ProgressReport] | None = None,
) -> evm.EarnedValueSnapshot:
    """The earned-value snapshot for ``project`` from its plan baseline and ``costs``.

    :func:`plan_baseline` says which version is the plan, resolved at this same
    ``as_of`` so a later approval cannot repaint an earlier render. Its time-phased
    lines, the task progress and the dated spend become calc value objects, then
    calc runs once. No approved plan means no lines, so BAC is 0 and every ratio
    derived from it is ``None`` — the snapshot an unbaselined project already
    returns. Collections are sorted so the float sums are byte-stable across runs.

    **An as-of the store cannot answer is refused, not answered with a number.**
    ``Task.percent_complete`` is a bare *current* reading: no column anywhere dates
    it, so the only date it truthfully speaks from is now. This used to hand calc one
    progress report per task stamped with ``as_of`` itself, which made today's
    percentage the measurement of whatever date was asked for — ``?as_of=2025-06-01``
    printing EV 500 and "50% complete" seven months before the project started, and an
    SPI in the tens for a month the plan had not begun. Where the store can *prove*
    the reading is not a measurement of that date — an ``as_of`` before the plan's
    earliest ``planned_start``, when no task was so much as due to be under way — the
    plan is dropped and the snapshot becomes the one a project with no approved plan
    already returns: BAC/PV/EV 0, spend still real, ratios ``None``. One empty state,
    not a second convention, and ``bac == 0`` is exactly the "nothing to assess"
    signal the cost and schedule evaluators, the rollup leaf and ``stamped_percent``
    already branch on — so neither an EV of 0 nor the CPI of 0 it would imply can
    paint such a date red. The risk evaluator reads BAC through
    :func:`remaining_budget`, and with nothing left to spend there is no reserve to
    hold and no share of one to express, so it answers "nothing to assess" and raises
    no threat — again, exactly what it already does for a project whose plan nobody
    has approved.

    PV and AC are genuinely time-phased and still answer every as-of, which is why
    the swept S-curves (``gather.business_curve``, ``views.evm_curve``,
    ``home._burn_series``) are untouched: they plot those two lines and never EV.
    Inside the plan window, ``progress`` is the dated series :func:`progress_history`
    replays out of the ChangeLog, and EV is read at the date asked for. **Omitting it
    resolves the same replay through the project's own session** (``object_session``)
    — it used to keep the undated current reading instead, so the report path printed
    EV 800 / CPI 2.00 at a backdated as-of the assessment on the same store answered
    with CPI 0.50 and rated red. One replay, every caller, no second convention. Only
    a project attached to no session at all — an in-memory value that has no store,
    so no ChangeLog could ever speak for it — falls back to one undated report per
    task carrying its current percentage, dated ``date.min`` so it answers every
    as-of: exactly the reading the replay itself gives a task with no logged history.
    """
    baseline = plan_baseline(project, as_of)
    lines = baseline.lines if baseline else []
    if lines and as_of < min(line.planned_start for line in lines):
        lines = []  # the plan had not begun: nothing to earn against, nothing to date
    ordered = sorted(lines, key=lambda line: line.task_id)
    plan = [
        evm.BaselineTask(str(x.task_id), x.planned_start, x.planned_finish, x.planned_cost)
        for x in ordered
    ]
    if progress is None:
        session = object_session(project)
        progress = progress_history(session, project, as_of) if session is not None else None
    done = (
        list(progress)
        if progress is not None
        else [
            evm.ProgressReport(str(x.task_id), date.min, x.task.percent_complete / 100)
            for x in ordered
        ]
    )
    spend = [
        evm.CostEntry(c.incurred_on, c.amount)
        for c in sorted(costs, key=lambda c: (c.incurred_on, c.id))
    ]
    return evm.earned_value_snapshot(plan, done, spend, as_of)


def project_costs(session: Session, project: Project) -> list[CostEntry]:
    """This project's cost entries, ordered so AC's float sum is stable."""
    rows = project_rows(session, CostEntry, project.id)
    return sorted(rows, key=lambda entry: (entry.incurred_on, entry.id))


def project_snapshot(session: Session, project: Project, as_of: date) -> evm.EarnedValueSnapshot:
    """Fetch this project's costs and dated progress, and compute its snapshot."""
    costs = project_costs(session, project)
    return snapshot_from(project, costs, as_of, progress_history(session, project, as_of))


def remaining_budget(snapshot: evm.EarnedValueSnapshot) -> float:
    """Budget still unspent against the baseline: BAC − AC, floored at zero."""
    return max(0.0, snapshot.bac - snapshot.ac)
