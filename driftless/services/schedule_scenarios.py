"""Schedule scenarios: crash, fast-track and levelling previews over
``pmbok.schedule_facts.ScheduleFacts``, and the one write this module offers —
``propose_baseline_change`` — which never edits the plan directly. It creates a
DRAFT ``Baseline`` (with ``BaselineLine`` rows carrying the scenario's dates) and
a ``ChangeRequest`` describing it, and stops there: approving the change and
promoting the draft to the live plan is the existing human step
(``PATCH /baselines/{id}`` then ``PATCH /change-requests/{id}``), never automated
here. A preview never reaches this module at all — ``web.assist_schedule``'s GET
route calls :func:`crashed_network`/:func:`fast_tracked_network` and the
``calc.network`` preview functions directly and writes nothing.

``crashed_network`` and ``fast_tracked_network`` are the one thing this module adds
to ``calc.network``'s own vocabulary: turning a crash/fast-track REQUEST into a
modified network, still never mutating the network handed in. They live here
rather than in ``calc.network`` because they are read by both the preview (GET,
read-only) and the write below, which recomputes the SAME scenario from the
request's raw parameters rather than trusting a client-submitted result — the
only number this module trusts from a caller is which task, which pair, and how
many days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.calc.network import (
    Activity,
    Dependency,
    ScheduleNetwork,
    backward_pass,
    critical_path,
    forward_pass,
    resource_levelling_preview,
)
from driftless.models import Baseline, BaselineLine, ChangeRequest, Project
from driftless.pmbok import catalog
from driftless.pmbok.schedule_facts import ScheduleFacts


class UnknownActivityError(ValueError):
    """A crash or fast-track request named a task this network does not have."""


class UnknownProcessError(ValueError):
    """``origin_process_id`` names no catalog process."""


def crashed_network(network: ScheduleNetwork, task_id: str, days: int) -> ScheduleNetwork:
    """``network`` with ``task_id``'s duration cut by ``days`` (floored at zero) —
    never mutates ``network``, the same "a scenario is a proposal" rule
    ``calc.network``'s own preview functions follow."""
    ids = {a.id for a in network.activities}
    if task_id not in ids:
        raise UnknownActivityError(task_id)
    activities = tuple(
        Activity(id=a.id, duration=max(a.duration - days, 0)) if a.id == task_id else a
        for a in network.activities
    )
    return ScheduleNetwork(activities=activities, dependencies=network.dependencies)


def fast_tracked_network(
    network: ScheduleNetwork, predecessor: str, successor: str
) -> ScheduleNetwork:
    """``network`` with the named finish-to-start pair turned start-to-start (its
    lag unchanged) — the one dependency a fast-tracking preview proposes
    overlapping. Never mutates ``network``; refuses a pair naming an unknown
    activity or one that is not an FS edge in this network."""
    ids = {a.id for a in network.activities}
    if predecessor not in ids or successor not in ids:
        raise UnknownActivityError(f"{predecessor}->{successor}")
    matched = False
    dependencies = []
    for dep in network.dependencies:
        if dep.predecessor == predecessor and dep.successor == successor and dep.kind == "FS":
            matched = True
            dependencies.append(Dependency(dep.predecessor, dep.successor, "SS", dep.lag))
        else:
            dependencies.append(dep)
    if not matched:
        raise UnknownActivityError(f"{predecessor}->{successor} is not an FS dependency")
    return ScheduleNetwork(activities=network.activities, dependencies=tuple(dependencies))


@dataclass(frozen=True)
class CrashInput:
    task_id: int
    days: int


@dataclass(frozen=True)
class FastTrackInput:
    predecessor_task_id: int
    successor_task_id: int


#: The scenario a proposal carries: a crash, a fast-track, or ``None`` for the
#: resource-levelling preview (levelling has no parameters — it proposes shifting
#: every non-critical activity to its own latest start).
ScenarioInput = CrashInput | FastTrackInput | None


def _scenario_network(facts: ScheduleFacts, scenario: ScenarioInput) -> ScheduleNetwork:
    if isinstance(scenario, CrashInput):
        return crashed_network(facts.network, str(scenario.task_id), scenario.days)
    if isinstance(scenario, FastTrackInput):
        return fast_tracked_network(
            facts.network, str(scenario.predecessor_task_id), str(scenario.successor_task_id)
        )
    return facts.network


def scenario_dates(
    facts: ScheduleFacts, scenario: ScenarioInput
) -> tuple[ScheduleNetwork, dict[str, int], dict[str, int]]:
    """The scenario's network plus each activity's proposed start/finish day-offset
    (from ``facts.anchor``) — the same figures both the GET preview and the write
    below present, computed once so neither can drift from the other."""
    network = _scenario_network(facts, scenario)
    early = forward_pass(network)
    durations = {a.id: a.duration for a in network.activities}
    if scenario is None:
        late = backward_pass(network, early)
        starts = dict(
            resource_levelling_preview(network, early, late, facts.demand).proposed_starts
        )
    else:
        starts = {aid: dates.early_start for aid, dates in early.items()}
    finishes = {aid: starts[aid] + durations[aid] for aid in starts}
    return network, starts, finishes


@dataclass(frozen=True)
class ScenarioSummary:
    """The finish, critical path and total cost ``scenario`` proposes — the SAME
    figures :func:`propose_baseline_change` would write into a draft baseline,
    read here without writing anything, so a preview can never disagree with the
    write it previews."""

    finish: date
    critical_paths: tuple[tuple[str, ...], ...]
    total_cost: float


def scenario_project_summary(facts: ScheduleFacts, scenario: ScenarioInput) -> ScenarioSummary:
    """``scenario``'s project finish, critical path(s) and total planned cost over
    ``facts`` — the one extension this module adds to :func:`scenario_dates` for a
    what-if preview: everything a reader needs to compare a scenario against the
    current plan (``scenario=None``) side by side, still never touching the network
    or the store. Crash cost is added the same way :func:`propose_baseline_change`
    adds it to a line's planned cost — the only cost a crash preview can honestly
    show, per this module's own docstring."""
    network, starts, finishes = scenario_dates(facts, scenario)
    early = forward_pass(network)
    late = backward_pass(network, early)
    finish_offset = max(finishes.values()) if finishes else 0
    original_durations = {a.id: a.duration for a in facts.network.activities}
    total_cost = 0.0
    for aid, start_offset in starts.items():
        cost = facts.planned_cost.get(aid, 0.0)
        if isinstance(scenario, CrashInput) and aid == str(scenario.task_id):
            crashed_days = original_durations.get(aid, 0) - (finishes[aid] - start_offset)
            cost += facts.cost_per_day.get(aid, 0.0) * crashed_days
        total_cost += cost
    return ScenarioSummary(
        finish=facts.anchor + timedelta(days=finish_offset),
        critical_paths=tuple(tuple(path) for path in critical_path(network, early, late)),
        total_cost=round(total_cost, 2),
    )


def propose_baseline_change(
    db: Session,
    project: Project,
    as_of: date,
    description: str,
    origin_process_id: str,
    facts: ScheduleFacts,
    scenario: ScenarioInput,
) -> tuple[ChangeRequest, Baseline]:
    """Write a draft ``Baseline`` (with lines) carrying ``scenario``'s proposed
    dates, plus the ``ChangeRequest`` describing why — and nothing else. The
    draft is not approved and the change is not resolved: promoting either is
    the existing human step, through the same generic write boundary every
    other baseline approval already goes through. ``ChangeRequest`` carries no
    actor column (neither does ``Baseline``/``BaselineLine``), so unlike
    ``services.technique_runs.record_run`` this write credits nobody by name —
    there is no field here for it to land in."""
    try:
        catalog.get(origin_process_id)
    except KeyError as error:
        raise UnknownProcessError(str(error)) from error

    original_durations = {a.id: a.duration for a in facts.network.activities}
    _, starts, finishes = scenario_dates(facts, scenario)

    # Picking the next unused version number to WRITE, not the plan to READ: it must
    # see every existing version, approved or not, or it would hand back a number
    # already taken and collide with the (project_id, version) unique constraint --
    # the same reason wizard.cli._next_baseline_version needs no approval filter.
    versions = db.scalars(select(Baseline.version).where(Baseline.project_id == project.id)).all()
    next_version = (max(versions) + 1) if versions else 1
    draft = Baseline(project_id=project.id, version=next_version, status="draft")
    db.add(draft)
    db.flush()

    for aid, start_offset in starts.items():
        cost = facts.planned_cost.get(aid, 0.0)
        if isinstance(scenario, CrashInput) and aid == str(scenario.task_id):
            crashed_days = original_durations.get(aid, 0) - (finishes[aid] - start_offset)
            cost += facts.cost_per_day.get(aid, 0.0) * crashed_days
        db.add(
            BaselineLine(
                baseline_id=draft.id,
                task_id=int(aid),
                planned_start=facts.anchor + timedelta(days=start_offset),
                planned_finish=facts.anchor + timedelta(days=finishes[aid]),
                planned_cost=round(cost, 2),
            )
        )

    change = ChangeRequest(
        project_id=project.id,
        description=description,
        raised_on=as_of,
        status="proposed",
        origin_process_id=origin_process_id,
    )
    db.add(change)
    db.commit()
    db.refresh(change)
    db.refresh(draft)
    return change, draft
