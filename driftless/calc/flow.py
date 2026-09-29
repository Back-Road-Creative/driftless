"""Kanban/flow metrics — pure functions over plain value objects.

No I/O, no ORM, no wall clock: every entry point takes an explicit ``as_of``,
the same discipline ``calc/evm.py`` and ``calc/forecast.py`` use, so a page or
report regenerates byte-identically from a pinned date. Nothing here imports
``driftless.models``, ``driftless.db`` or another ``driftless.calc`` module
except ``calc.forecast`` (see ``release_forecast`` below) — the caller adapts
stored rows into ``WorkItem`` and the caller decides which items belong to
which iteration; this module has no notion of a sprint boundary of its own.

**A single work item.** Three optional dates trace one item's whole life:
``created_on`` (always set), ``started_on`` (set once work begins) and
``done_on`` (set once it is finished). An item can be created and finished
without ever recording a start; an item cannot finish before it starts, or
start before it was created — both are refused at construction.

**"As of" excludes the future.** Every function here reads ``as_of`` as
"what would this figure have read at the end of that day" — a ``done_on``
after ``as_of`` counts nowhere, exactly as ``evm``'s costs and progress
readings ignore anything dated past the report date.

**Cycle time vs. lead time.** Cycle time is started-to-done: how long active
work took once someone picked it up. Lead time is created-to-done: how long a
requester actually waited. Both are reported as ``DurationStats`` (count,
median, p85) built over the same percentile helper, so the two never drift
apart from restating the same arithmetic twice.

**Burndown vs. burnup.** Burndown assumes the scope handed to it is fixed —
``remaining_points`` is that fixed total minus what had finished by each day,
heading toward zero. Burnup instead reports two lines, scope and completed,
because scope is allowed to grow: a day's scope is every item that existed
(``created_on <= day``) by then, which is exactly how new work joining an
iteration shows up as a rising scope line rather than a silently moving
target.

**Release forecasting is not re-derived here.** ``release_forecast`` is a
thin pass-through to ``calc.forecast.forecast_completion`` — the flow layer's
name for the same band, over the same ``Sprint`` history, so there is one
velocity rule in the codebase, not a flow-flavoured second one that could
disagree with it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from driftless.calc.forecast import CompletionBand, Sprint, forecast_completion

__all__ = [
    "WorkItem",
    "DurationStats",
    "BurndownPoint",
    "BurnupPoint",
    "CumulativeFlowPoint",
    "wip",
    "throughput",
    "cycle_time",
    "lead_time",
    "burndown",
    "burnup",
    "cumulative_flow",
    "release_forecast",
]


@dataclass(frozen=True)
class WorkItem:
    """One piece of work, traced by up to three dates plus its size."""

    id: str
    created_on: date
    started_on: date | None
    done_on: date | None
    points: float

    def __post_init__(self) -> None:
        if self.points < 0:
            raise ValueError(f"item {self.id}: points is negative")
        if self.started_on is not None and self.started_on < self.created_on:
            raise ValueError(f"item {self.id}: started_on precedes created_on")
        if self.done_on is not None:
            if self.done_on < self.created_on:
                raise ValueError(f"item {self.id}: done_on precedes created_on")
            if self.started_on is not None and self.done_on < self.started_on:
                raise ValueError(f"item {self.id}: done_on precedes started_on")


@dataclass(frozen=True)
class DurationStats:
    """Median and p85 of a set of durations (days), plus the sample size behind them."""

    count: int
    median: float | None
    p85: float | None


@dataclass(frozen=True)
class BurndownPoint:
    """One day of a burndown: points still remaining out of a fixed total."""

    day: date
    remaining_points: float


@dataclass(frozen=True)
class BurnupPoint:
    """One day of a burnup: points completed against the scope known by then."""

    day: date
    completed_points: float
    scope_points: float


@dataclass(frozen=True)
class CumulativeFlowPoint:
    """One day's item count in each of the three states this module tracks."""

    day: date
    not_started: int
    in_progress: int
    done: int


def _percentile(ordered: Sequence[int], fraction: float) -> float:
    """Nearest-rank percentile over an already-sorted, non-empty sequence."""
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return float(ordered[index])


def wip(items: Sequence[WorkItem], as_of: date) -> int:
    """Work in progress at end of ``as_of``: started, and not yet done (or done later)."""
    return sum(
        1
        for item in items
        if item.started_on is not None
        and item.started_on <= as_of
        and (item.done_on is None or item.done_on > as_of)
    )


def throughput(items: Sequence[WorkItem], window_start: date, as_of: date) -> int:
    """Count of items finished in ``[window_start, as_of]``, both ends inclusive."""
    if window_start > as_of:
        raise ValueError("window_start must be on or before as_of")
    return sum(
        1 for item in items if item.done_on is not None and window_start <= item.done_on <= as_of
    )


def _duration_stats(durations: list[int]) -> DurationStats:
    if not durations:
        return DurationStats(count=0, median=None, p85=None)
    ordered = sorted(durations)
    return DurationStats(
        count=len(ordered),
        median=_percentile(ordered, 0.5),
        p85=_percentile(ordered, 0.85),
    )


def cycle_time(items: Sequence[WorkItem], as_of: date) -> DurationStats:
    """Started-to-done durations (days) for items finished on or before ``as_of``.

    An item with no recorded start never contributes — it has no cycle to time.
    """
    durations = [
        (item.done_on - item.started_on).days
        for item in items
        if item.started_on is not None and item.done_on is not None and item.done_on <= as_of
    ]
    return _duration_stats(durations)


def lead_time(items: Sequence[WorkItem], as_of: date) -> DurationStats:
    """Created-to-done durations (days) for items finished on or before ``as_of``."""
    durations = [
        (item.done_on - item.created_on).days
        for item in items
        if item.done_on is not None and item.done_on <= as_of
    ]
    return _duration_stats(durations)


def burndown(
    items: Sequence[WorkItem], iteration_start: date, iteration_end: date, as_of: date
) -> list[BurndownPoint]:
    """One point per day from ``iteration_start`` to ``min(iteration_end, as_of)``.

    ``remaining_points`` is the fixed total of ``items`` minus whatever had a
    ``done_on`` on or before that day. Raises ``ValueError`` if the iteration
    window is inverted. ``as_of`` before ``iteration_start`` yields an empty
    series — the iteration has no history yet to plot.
    """
    if iteration_end < iteration_start:
        raise ValueError("iteration_end precedes iteration_start")
    last_day = min(iteration_end, as_of)
    if last_day < iteration_start:
        return []
    total_points = sum(item.points for item in items)
    points: list[BurndownPoint] = []
    day = iteration_start
    while day <= last_day:
        done_points = sum(
            item.points for item in items if item.done_on is not None and item.done_on <= day
        )
        points.append(BurndownPoint(day=day, remaining_points=total_points - done_points))
        day += timedelta(days=1)
    return points


def burnup(
    items: Sequence[WorkItem], iteration_start: date, iteration_end: date, as_of: date
) -> list[BurnupPoint]:
    """One point per day from ``iteration_start`` to ``min(iteration_end, as_of)``.

    ``scope_points`` is every item that existed by that day (``created_on <=
    day``); ``completed_points`` is the subset of those also done by then. Same
    window rules as ``burndown``.
    """
    if iteration_end < iteration_start:
        raise ValueError("iteration_end precedes iteration_start")
    last_day = min(iteration_end, as_of)
    if last_day < iteration_start:
        return []
    points: list[BurnupPoint] = []
    day = iteration_start
    while day <= last_day:
        scope_points = sum(item.points for item in items if item.created_on <= day)
        completed_points = sum(
            item.points for item in items if item.done_on is not None and item.done_on <= day
        )
        points.append(
            BurnupPoint(day=day, completed_points=completed_points, scope_points=scope_points)
        )
        day += timedelta(days=1)
    return points


def cumulative_flow(
    items: Sequence[WorkItem], start: date, as_of: date
) -> list[CumulativeFlowPoint]:
    """One point per day from ``start`` to ``as_of``, counting items per state.

    An item not yet created (``created_on > day``) is not counted in any
    bucket that day. ``as_of`` before ``start`` yields an empty series.
    """
    if as_of < start:
        return []
    points: list[CumulativeFlowPoint] = []
    day = start
    while day <= as_of:
        not_started = in_progress = done = 0
        for item in items:
            if item.created_on > day:
                continue
            if item.done_on is not None and item.done_on <= day:
                done += 1
            elif item.started_on is not None and item.started_on <= day:
                in_progress += 1
            else:
                not_started += 1
        points.append(
            CumulativeFlowPoint(
                day=day, not_started=not_started, in_progress=in_progress, done=done
            )
        )
        day += timedelta(days=1)
    return points


def release_forecast(
    history: Sequence[Sprint], remaining_points: float, as_of: date
) -> CompletionBand:
    """The flow layer's name for ``calc.forecast.forecast_completion``.

    Pure pass-through — no second velocity rule lives here. See that
    function's docstring for the band's meaning and its edge-case behaviour.
    """
    return forecast_completion(history, remaining_points, as_of)
