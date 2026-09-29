"""The schedule network — precedence, leads and lags, critical path and float.

Pure functions over plain value objects, same discipline as ``calc.evm``: no
I/O, no ORM, no wall clock, and nothing here imports another ``driftless.calc``
module. The caller adapts stored tasks into ``Activity``/``Dependency`` pairs;
this module only does the arithmetic.

**The four dependency kinds.** A ``Dependency`` names its ``kind`` explicitly
rather than assuming finish-to-start: ``FS`` (successor cannot start before
the predecessor finishes — the common case), ``SS`` (cannot start before the
predecessor starts), ``FF`` (cannot finish before the predecessor finishes),
``SF`` (cannot finish before the predecessor starts). ``lag`` is calendar days
added to the constraint; a negative ``lag`` is a lead — the successor may
begin that many days before the constraint would otherwise allow.

**Forward and backward pass.** ``forward_pass`` walks the network in
topological order computing each activity's earliest possible start and
finish (ES/EF) from its predecessors. ``backward_pass`` walks it in reverse,
computing the latest an activity can start or finish (LS/LF) without pushing
out the project finish date. Both refuse a cycle by naming the activities
caught in it, and refuse a dependency naming an activity that is not in the
network — a dangling reference is not silently ignored.

**Float.** ``total_float`` is how far an activity can slip without moving the
project finish (LS - ES); zero means the activity is on the critical path.
``free_float`` is the tighter number: how far it can slip without delaying
any successor's own earliest start, which can be less than total float even
on a non-critical activity.

**Scenarios, never edits.** ``schedule_compression_preview`` and
``resource_levelling_preview`` return a proposal — which activities crashing
would touch, which finish-to-start pairs fast-tracking could overlap, what a
levelled set of starts would look like — and never mutate the network handed
in. Applying a scenario is a decision for whoever calls this code, not
something the calculator does on its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

DependencyKind = Literal["FS", "SS", "FF", "SF"]


@dataclass(frozen=True)
class Activity:
    """One schedulable unit of work: an id and a duration in whole days."""

    id: str
    duration: int

    def __post_init__(self) -> None:
        if self.duration < 0:
            raise ValueError(f"activity {self.id}: duration is negative")


@dataclass(frozen=True)
class Dependency:
    """A precedence relationship between two activities. A negative ``lag``
    is a lead: the successor may start that many days early."""

    predecessor: str
    successor: str
    kind: DependencyKind
    lag: int = 0


@dataclass(frozen=True)
class ScheduleNetwork:
    """Activities plus the dependencies between them, validated at
    construction: no dependency may name an activity that is not present."""

    activities: tuple[Activity, ...]
    dependencies: tuple[Dependency, ...]

    def __post_init__(self) -> None:
        ids = {a.id for a in self.activities}
        if len(ids) != len(self.activities):
            raise ValueError("schedule network: duplicate activity id")
        for dep in self.dependencies:
            for activity_id in (dep.predecessor, dep.successor):
                if activity_id not in ids:
                    raise ValueError(
                        f"schedule network: dependency names unknown activity {activity_id!r}"
                    )


@dataclass(frozen=True)
class EarlyDates:
    """Earliest an activity can start and finish, from the forward pass."""

    early_start: int
    early_finish: int


@dataclass(frozen=True)
class LateDates:
    """Latest an activity can start and finish without slipping the project,
    from the backward pass."""

    late_start: int
    late_finish: int


def _by_id(network: ScheduleNetwork) -> dict[str, Activity]:
    return {a.id: a for a in network.activities}


def _topological_order(network: ScheduleNetwork) -> list[str]:
    """Kahn's algorithm. Refuses with a plain message naming every activity
    still stuck in a cycle once no activity with in-degree zero is left."""
    predecessors: dict[str, set[str]] = {a.id: set() for a in network.activities}
    successors: dict[str, set[str]] = {a.id: set() for a in network.activities}
    for dep in network.dependencies:
        predecessors[dep.successor].add(dep.predecessor)
        successors[dep.predecessor].add(dep.successor)

    ready = sorted(aid for aid, preds in predecessors.items() if not preds)
    order: list[str] = []
    remaining = {aid: len(preds) for aid, preds in predecessors.items()}
    while ready:
        current = ready.pop(0)
        order.append(current)
        for successor in sorted(successors[current]):
            remaining[successor] -= 1
            if remaining[successor] == 0:
                ready.append(successor)

    if len(order) != len(network.activities):
        stuck = sorted(aid for aid, left in remaining.items() if left > 0)
        raise ValueError(f"schedule network: cycle among activities {stuck}")
    return order


def forward_pass(network: ScheduleNetwork) -> dict[str, EarlyDates]:
    """ES/EF per activity. An activity with no predecessors starts at day 0."""
    activities = _by_id(network)
    order = _topological_order(network)
    incoming: dict[str, list[Dependency]] = {a.id: [] for a in network.activities}
    for dep in network.dependencies:
        incoming[dep.successor].append(dep)

    early: dict[str, EarlyDates] = {}
    for activity_id in order:
        duration = activities[activity_id].duration
        contributions = [0]
        for dep in incoming[activity_id]:
            pred = early[dep.predecessor]
            if dep.kind == "FS":
                contributions.append(pred.early_finish + dep.lag)
            elif dep.kind == "SS":
                contributions.append(pred.early_start + dep.lag)
            elif dep.kind == "FF":
                contributions.append(pred.early_finish + dep.lag - duration)
            else:  # SF
                contributions.append(pred.early_start + dep.lag - duration)
        early_start = max(contributions)
        early[activity_id] = EarlyDates(early_start, early_start + duration)
    return early


def backward_pass(
    network: ScheduleNetwork, early: Mapping[str, EarlyDates]
) -> dict[str, LateDates]:
    """LS/LF per activity, given ``early`` from ``forward_pass``. An activity
    with no successors is late-finished at the project's own finish date."""
    activities = _by_id(network)
    order = _topological_order(network)
    outgoing: dict[str, list[Dependency]] = {a.id: [] for a in network.activities}
    for dep in network.dependencies:
        outgoing[dep.predecessor].append(dep)

    project_finish = max((dates.early_finish for dates in early.values()), default=0)
    late: dict[str, LateDates] = {}
    for activity_id in reversed(order):
        duration = activities[activity_id].duration
        contributions = [project_finish] if not outgoing[activity_id] else []
        for dep in outgoing[activity_id]:
            succ = late[dep.successor]
            if dep.kind == "FS":
                contributions.append(succ.late_start - dep.lag)
            elif dep.kind == "SS":
                contributions.append(succ.late_start - dep.lag + duration)
            elif dep.kind == "FF":
                contributions.append(succ.late_finish - dep.lag)
            else:  # SF
                contributions.append(succ.late_finish - dep.lag + duration)
        late_finish = min(contributions)
        late[activity_id] = LateDates(late_finish - duration, late_finish)
    return late


@dataclass(frozen=True)
class Disagreement:
    """One activity whose baseline's own STORED start/finish falls outside
    ``[ES, LF]``, or whose stored span is not its own duration — a real
    contradiction, never a task merely inside its own float. Read-only."""

    activity_id: str
    stored_start: int
    early_start: int
    stored_finish: int
    late_finish: int


def network_disagreements(
    network: ScheduleNetwork,
    stored_start: Mapping[str, int],
    stored_finish: Mapping[str, int],
    tolerance: int = 0,
) -> tuple[Disagreement, ...]:
    """Every activity whose stored start precedes ``ES``, stored finish
    follows ``LF``, or whose stored span is not its own duration, past
    ``tolerance`` days — sorted by activity id. Anywhere inside ``[ES, LF]``
    at its own duration is agreement: a task's own float. A stored mapping
    missing the activity skips it, never guessed at — and so does an activity
    with no dependency edge at all: an isolated task carries no recorded
    precedence to disagree with, so ``LF`` collapsing to the WHOLE network's
    project finish (the textbook rule for any leaf) would be a false
    contradiction, not a real one, for a task the network never claimed
    anything about."""
    early = forward_pass(network)
    late = backward_pass(network, early)
    durations = {a.id: a.duration for a in network.activities}
    connected = {dep.predecessor for dep in network.dependencies} | {
        dep.successor for dep in network.dependencies
    }
    disagreements = []
    for activity_id, dates in early.items():
        if activity_id not in stored_start or activity_id not in stored_finish:
            continue
        if activity_id not in connected:
            continue
        s, f = stored_start[activity_id], stored_finish[activity_id]
        late_finish = late[activity_id].late_finish
        span_wrong = abs((f - s) - durations[activity_id]) > tolerance
        outside_window = s < dates.early_start - tolerance or f > late_finish + tolerance
        if span_wrong or outside_window:
            disagreements.append(Disagreement(activity_id, s, dates.early_start, f, late_finish))
    return tuple(sorted(disagreements, key=lambda d: d.activity_id))


def total_float(early: Mapping[str, EarlyDates], late: Mapping[str, LateDates]) -> dict[str, int]:
    """LS - ES per activity (equally LF - EF). Zero means critical."""
    return {aid: late[aid].late_start - early[aid].early_start for aid in early}


def free_float(
    network: ScheduleNetwork, early: Mapping[str, EarlyDates], late: Mapping[str, LateDates]
) -> dict[str, int]:
    """How far an activity can slip without delaying any successor's own ES.
    An activity with no successors is bounded only by the project finish, so
    its free float equals its total float."""
    outgoing: dict[str, list[Dependency]] = {a.id: [] for a in network.activities}
    for dep in network.dependencies:
        outgoing[dep.predecessor].append(dep)
    floats = total_float(early, late)

    result: dict[str, int] = {}
    for activity_id, dates in early.items():
        deps = outgoing[activity_id]
        if not deps:
            result[activity_id] = floats[activity_id]
            continue
        slacks = []
        for dep in deps:
            succ = early[dep.successor]
            if dep.kind == "FS":
                slacks.append(succ.early_start - (dates.early_finish + dep.lag))
            elif dep.kind == "SS":
                slacks.append(succ.early_start - (dates.early_start + dep.lag))
            elif dep.kind == "FF":
                slacks.append(succ.early_finish - (dates.early_finish + dep.lag))
            else:  # SF
                slacks.append(succ.early_finish - (dates.early_start + dep.lag))
        result[activity_id] = min(slacks)
    return result


def critical_path(
    network: ScheduleNetwork,
    early: Mapping[str, EarlyDates],
    late: Mapping[str, LateDates],
) -> tuple[tuple[str, ...], ...]:
    """Every zero-float path from a start activity to an end activity, not
    just one — a network can have several critical paths tied at the same
    project finish date."""
    floats = total_float(early, late)
    critical_ids = {aid for aid, f in floats.items() if f == 0}
    critical_edges: dict[str, list[str]] = {aid: [] for aid in critical_ids}
    has_critical_predecessor = set()
    for dep in network.dependencies:
        if dep.predecessor in critical_ids and dep.successor in critical_ids:
            critical_edges[dep.predecessor].append(dep.successor)
            has_critical_predecessor.add(dep.successor)

    starts = sorted(aid for aid in critical_ids if aid not in has_critical_predecessor)

    paths: list[tuple[str, ...]] = []

    def _walk(activity_id: str, so_far: tuple[str, ...]) -> None:
        so_far = so_far + (activity_id,)
        successors = sorted(critical_edges[activity_id])
        if not successors:
            paths.append(so_far)
            return
        for successor in successors:
            _walk(successor, so_far)

    for start in starts:
        _walk(start, ())
    return tuple(sorted(paths))


@dataclass(frozen=True)
class DiagramNode:
    """One activity, sized and flagged for a later SVG renderer. Mirrors the
    id/kind/label shape of ``driftless.pmbok.graph.Node``."""

    id: str
    kind: Literal["activity"]
    label: str
    critical: bool


@dataclass(frozen=True)
class DiagramEdge:
    """One dependency. Mirrors the source/target/kind/flag shape of
    ``driftless.pmbok.graph.Edge``; ``critical`` stands in for ``optional``."""

    source: str
    target: str
    kind: DependencyKind
    critical: bool


@dataclass(frozen=True)
class NetworkDiagram:
    """The whole network as nodes and edges, immutable tuples."""

    nodes: tuple[DiagramNode, ...]
    edges: tuple[DiagramEdge, ...]


def network_diagram(
    network: ScheduleNetwork,
    early: Mapping[str, EarlyDates],
    late: Mapping[str, LateDates],
) -> NetworkDiagram:
    """The network as a diagram, each node and each edge between two critical
    activities flagged, ready for the method map's SVG style."""
    floats = total_float(early, late)
    nodes = tuple(
        DiagramNode(
            id=a.id,
            kind="activity",
            label=f"{a.id} ({a.duration}d)",
            critical=floats[a.id] == 0,
        )
        for a in network.activities
    )
    edges = tuple(
        DiagramEdge(
            source=dep.predecessor,
            target=dep.successor,
            kind=dep.kind,
            critical=floats[dep.predecessor] == 0 and floats[dep.successor] == 0,
        )
        for dep in network.dependencies
    )
    return NetworkDiagram(nodes=nodes, edges=edges)


@dataclass(frozen=True)
class FastTrackCandidate:
    """One finish-to-start pair on the critical path that could be
    overlapped instead — the fast-tracking technique."""

    predecessor: str
    successor: str


@dataclass(frozen=True)
class CrashCandidate:
    """One critical-path activity that could be shortened, at the given
    cost per day removed — the crashing technique."""

    activity_id: str
    cost_per_day: float


@dataclass(frozen=True)
class CompressionScenario:
    """A compression proposal. Nothing here has been applied — it is a menu
    of options, cheapest crash candidate first, for a human to choose from."""

    crash_candidates: tuple[CrashCandidate, ...]
    fast_track_candidates: tuple[FastTrackCandidate, ...]


def schedule_compression_preview(
    network: ScheduleNetwork,
    early: Mapping[str, EarlyDates],
    late: Mapping[str, LateDates],
    cost_per_day: Mapping[str, float],
) -> CompressionScenario:
    """Which critical-path activities could be crashed, and which
    finish-to-start critical pairs could be fast-tracked. Never edits
    ``network``: the caller decides whether to act on either list."""
    floats = total_float(early, late)
    critical_ids = {aid for aid, f in floats.items() if f == 0}

    crash_candidates = tuple(
        sorted(
            (
                CrashCandidate(activity_id=aid, cost_per_day=cost_per_day[aid])
                for aid in critical_ids
                if aid in cost_per_day
            ),
            key=lambda candidate: (candidate.cost_per_day, candidate.activity_id),
        )
    )
    fast_track_candidates = tuple(
        sorted(
            (
                FastTrackCandidate(predecessor=dep.predecessor, successor=dep.successor)
                for dep in network.dependencies
                if dep.kind == "FS"
                and dep.lag >= 0
                and dep.predecessor in critical_ids
                and dep.successor in critical_ids
            ),
            key=lambda candidate: (candidate.predecessor, candidate.successor),
        )
    )
    return CompressionScenario(
        crash_candidates=crash_candidates, fast_track_candidates=fast_track_candidates
    )


@dataclass(frozen=True)
class ResourceLevellingScenario:
    """A naive levelling proposal: non-critical activities pushed to their
    latest start, critical ones left at their earliest. Not a solver — just
    one alternative schedule to weigh against the earliest-start one, never
    applied by this function."""

    proposed_starts: Mapping[str, int]
    peak_demand_before: float
    peak_demand_after: float


def _peak_demand(
    starts: Mapping[str, int], durations: Mapping[str, int], demand: Mapping[str, float]
) -> float:
    daily: dict[int, float] = {}
    for activity_id, start in starts.items():
        for day in range(start, start + durations[activity_id]):
            daily[day] = daily.get(day, 0.0) + demand.get(activity_id, 0.0)
    return max(daily.values(), default=0.0)


def resource_levelling_preview(
    network: ScheduleNetwork,
    early: Mapping[str, EarlyDates],
    late: Mapping[str, LateDates],
    demand: Mapping[str, float],
) -> ResourceLevellingScenario:
    """Preview shifting every non-critical activity to its late start, to see
    whether that alone lowers the daily peak demand. Never mutates
    ``network`` or ``early``/``late`` — a scenario to weigh, not a plan edit."""
    floats = total_float(early, late)
    durations = {a.id: a.duration for a in network.activities}
    earliest_starts = {aid: dates.early_start for aid, dates in early.items()}
    proposed_starts = {
        aid: (earliest_starts[aid] if floats[aid] == 0 else late[aid].late_start)
        for aid in earliest_starts
    }
    return ResourceLevellingScenario(
        proposed_starts=proposed_starts,
        peak_demand_before=_peak_demand(earliest_starts, durations, demand),
        peak_demand_after=_peak_demand(proposed_starts, durations, demand),
    )
