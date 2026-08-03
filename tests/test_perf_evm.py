"""F-P1: ``earned_value`` reads a per-call index, not a linear scan per task.

``percent_complete_at`` walks every progress reading to answer for one task;
calling it once per baseline task made ``earned_value`` quadratic — 185x
slower from 100 to 1,600 tasks — and it sits under every dashboard snapshot.
The correctness half pins the result to the per-task definition (which keeps
the original scan) over a multi-reading history: superseded readings, a
reading past the as-of, a same-day tie, and a task with no readings at all.
The shape half counts traversals of the progress sequence itself: one per
``earned_value`` call, however many tasks the baseline holds.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import date
from typing import overload

from driftless.calc.evm import (
    BaselineTask,
    ProgressReport,
    earned_value,
    percent_complete_at,
)

BASELINE = (
    BaselineTask("A", date(2026, 1, 1), date(2026, 1, 10), 1000.0),
    BaselineTask("B", date(2026, 1, 1), date(2026, 1, 10), 2000.0),
    BaselineTask("C", date(2026, 1, 6), date(2026, 1, 15), 3000.0),
    BaselineTask("D", date(2026, 1, 6), date(2026, 1, 15), 4000.0),
)

# Deliberately unsorted. A's 0.2 is superseded and its 0.9 postdates the
# as-of; B's two readings tie on the date, and the FIRST in sequence wins,
# exactly as ``max`` broke the tie in the scan; C reports only after the
# as-of; D never reports.
PROGRESS = (
    ProgressReport("B", date(2026, 1, 5), 0.5),
    ProgressReport("A", date(2026, 1, 8), 0.6),
    ProgressReport("A", date(2026, 1, 3), 0.2),
    ProgressReport("B", date(2026, 1, 5), 0.1),
    ProgressReport("C", date(2026, 1, 20), 1.0),
    ProgressReport("A", date(2026, 1, 12), 0.9),
)

AS_OF = date(2026, 1, 10)


class CountingProgress(Sequence[ProgressReport]):
    """A progress sequence that counts how many times it is traversed."""

    def __init__(self, readings: Sequence[ProgressReport]) -> None:
        self._readings = tuple(readings)
        self.traversals = 0

    def __len__(self) -> int:
        return len(self._readings)

    @overload
    def __getitem__(self, index: int) -> ProgressReport: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[ProgressReport]: ...

    def __getitem__(self, index: int | slice) -> ProgressReport | Sequence[ProgressReport]:
        return self._readings[index]

    def __iter__(self) -> Iterator[ProgressReport]:
        self.traversals += 1
        return iter(self._readings)


def test_earned_value_pins_the_multi_reading_history() -> None:
    # A 60% x 1,000 + B 50% x 2,000 (first of the tied pair); C and D earn 0.
    assert earned_value(BASELINE, PROGRESS, AS_OF) == 1600.0


def test_earned_value_matches_the_per_task_definition_at_every_as_of() -> None:
    for as_of in (date(2025, 12, 31), date(2026, 1, 4), AS_OF, date(2026, 1, 25)):
        expected = sum(
            task.planned_cost * percent_complete_at(PROGRESS, task.task_id, as_of)
            for task in BASELINE
        )
        assert earned_value(BASELINE, PROGRESS, as_of) == expected


def test_earned_value_traverses_progress_once_however_many_tasks() -> None:
    baseline = [
        BaselineTask(f"T{i:04d}", date(2026, 1, 1), date(2026, 1, 10), 100.0) for i in range(50)
    ]
    readings = CountingProgress(
        [ProgressReport(task.task_id, date(2026, 1, 5), 0.5) for task in baseline]
    )
    assert earned_value(baseline, readings, AS_OF) == 2500.0
    assert readings.traversals == 1, (
        f"progress was traversed {readings.traversals} times for one earned_value call — "
        "the per-task linear scan is back"
    )
