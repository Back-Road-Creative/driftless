"""``schedule_facts``: one project's schedule network, adapted from stored rows into
``driftless.calc.network``'s pure inputs, as of a date.

Mirrors ``web.gantt``'s own read exactly — the newest *approved* baseline visible at
``as_of`` (``assess.adapters.approved_as_of``, the same gate the Gantt page and the
capacity heatmap use) — so this page's network can never disagree with the bars the
Gantt page already draws for the same as-of. No approved baseline with lines means no
network to build: ``None``, the same "no plan yet" reading gantt.py gives.

An ``Activity``'s duration is its baseline line's planned window in days, never a raw
``Task.estimate`` — the estimate is points or hours depending on delivery mode and
carries no calendar meaning by itself; the planned window is the one figure already
translated into days. ``TaskDependency`` rows are scoped to the tasks that have a line
in this baseline, so an edge naming a task outside the plan cannot appear in the
network calc.network.ScheduleNetwork would refuse anyway.

Two fields here are proxies over data the store actually has, not stored crash costs
or resource-loading figures nothing in the schema tracks yet — each says so:

* ``cost_per_day`` — a task's planned cost spread evenly across its planned days. The
  best crash-cost figure the stored plan can honestly offer; a real crash cost (marginal
  cost of one FEWER day, which is usually higher than the average) is not stored anywhere.
* ``demand`` — 1.0 when a task carries an assignee, 0.0 otherwise: a headcount proxy for
  resource-levelling, since no separate resource-loading figure exists per task either.

``three_point_safety`` is PMBOK's own basis for a critical-chain buffer: the spread
between a task's pessimistic and most-likely three-point estimate (``high - value`` on
an ``EstimateScenario`` naming the task, target ``"duration"``). A task with no such
estimate on record contributes no safety — never an invented number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import set_committed_value

from driftless.assess.adapters import plan_baseline
from driftless.calc.network import Activity, Dependency, DependencyKind, ScheduleNetwork
from driftless.models import Baseline, BaselineLine, Project, TaskDependency
from driftless.models.schedule import EstimateScenario


@dataclass(frozen=True)
class ScheduleFacts:
    """Everything ``calc.network`` needs for one project as of a date, plus the
    display and scenario facts the stored plan can honestly support."""

    baseline_version: int
    anchor: date  # day 0 for the network's day-offsets: the plan's earliest planned_start
    network: ScheduleNetwork
    task_names: dict[str, str]  # activity id (task pk, as str) -> task name
    planned_cost: dict[str, float]  # activity id -> its current baseline line's planned cost
    cost_per_day: dict[str, float]  # crash-cost proxy: see module docstring
    demand: dict[str, float]  # levelling-demand proxy: see module docstring
    three_point_safety: dict[str, float]  # critical-chain safety: see module docstring


def schedule_facts(db: Session, project: Project, as_of: date) -> ScheduleFacts | None:
    """``project``'s schedule network as of ``as_of``, or ``None`` when there is no
    approved, lined baseline yet to build one from.

    Picks the baseline through :func:`assess.adapters.plan_baseline` — the SAME
    "newest approved, visible at as_of" rule ``approved_as_of`` gives the Gantt
    page and the capacity heatmap, just read off an already-loaded ``Project``
    instead of run as a second query. ``project.baselines`` is a ``viewonly``
    relationship (``models.hierarchy.Project.baselines``); this function is the
    one place that reads every version's lines and their tasks in one batch and
    seeds it onto ``project`` via ``set_committed_value`` (never a plain
    attribute assignment, which a ``viewonly`` collection does not treat as
    "loaded" and would re-query on next access). The schedule page's own
    scenario-preview reads (``assess.adapters.project_snapshot``, via
    ``web.assist_schedule``) call ``plan_baseline`` on this SAME ``project``
    object right after, over the SAME request; because the collection is
    already seeded, that second call fires no query of its own — the fix for
    the ceiling this module used to blow past, where a scenario-preview render
    redundantly re-queried a baseline and its lines this function had already
    fetched."""
    baselines = db.scalars(
        select(Baseline)
        .where(Baseline.project_id == project.id)
        .options(selectinload(Baseline.lines).selectinload(BaselineLine.task))
    ).all()
    set_committed_value(project, "baselines", list(baselines))
    baseline = plan_baseline(project, as_of)
    if baseline is None:
        return None
    lines = sorted(baseline.lines, key=lambda line: line.task_id)
    if not lines:
        return None

    activities: list[Activity] = []
    task_names: dict[str, str] = {}
    planned_cost: dict[str, float] = {}
    cost_per_day: dict[str, float] = {}
    demand: dict[str, float] = {}
    anchor = min(line.planned_start for line in lines)
    for line in lines:
        aid = str(line.task_id)
        duration = max((line.planned_finish - line.planned_start).days, 0)
        activities.append(Activity(id=aid, duration=duration))
        task_names[aid] = line.task.name
        planned_cost[aid] = line.planned_cost
        cost_per_day[aid] = (line.planned_cost / duration) if duration else 0.0
        demand[aid] = 1.0 if line.task.assignee_id is not None else 0.0

    task_ids = {line.task_id for line in lines}
    dep_rows = db.scalars(
        select(TaskDependency)
        .where(
            TaskDependency.predecessor_task_id.in_(task_ids),
            TaskDependency.successor_task_id.in_(task_ids),
        )
        .order_by(TaskDependency.id)
    ).all()
    dependencies = tuple(
        Dependency(
            predecessor=str(dep.predecessor_task_id),
            successor=str(dep.successor_task_id),
            kind=cast(DependencyKind, dep.kind),
            lag=dep.lag_days,
        )
        for dep in dep_rows
    )
    network = ScheduleNetwork(activities=tuple(activities), dependencies=dependencies)

    three_point_safety: dict[str, float] = {}
    estimates = db.scalars(
        select(EstimateScenario).where(
            EstimateScenario.project_id == project.id,
            EstimateScenario.target == "duration",
            EstimateScenario.kind == "three_point",
            EstimateScenario.subject_task_id.in_(task_ids),
            EstimateScenario.high.is_not(None),
        )
    ).all()
    for estimate in estimates:
        aid = str(estimate.subject_task_id)
        # A task may carry more than one estimate over time; the largest safety on
        # record is kept rather than an arbitrary "last one read".
        safety = cast(float, estimate.high) - estimate.value
        three_point_safety[aid] = max(three_point_safety.get(aid, 0.0), safety)

    return ScheduleFacts(
        baseline_version=baseline.version,
        anchor=anchor,
        network=network,
        task_names=task_names,
        planned_cost=planned_cost,
        cost_per_day=cost_per_day,
        demand=demand,
        three_point_safety=three_point_safety,
    )
