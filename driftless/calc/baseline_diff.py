"""Per-line delta between two baseline versions — dates, cost and scope. Pure
functions over plain value objects, exactly like ``calc.evm``: no I/O, no ORM,
no wall clock. The caller adapts stored ``BaselineLine`` rows into
``driftless.calc.evm.BaselineTask`` — the same value object ``calc.evm`` and
``calc.cost`` already use — and this module never re-derives that adaptation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from driftless.calc.evm import BaselineTask


@dataclass(frozen=True)
class BaselineLineDiff:
    """One task's before/after slice. ``None`` on a side means the task is not on
    that baseline: absent on ``before`` is a task ADDED to scope by the later
    version, absent on ``after`` is one REMOVED from it."""

    task_id: str
    start_before: date | None
    start_after: date | None
    finish_before: date | None
    finish_after: date | None
    cost_before: float | None
    cost_after: float | None

    @property
    def status(self) -> str:
        if self.start_before is None:
            return "added"
        if self.start_after is None:
            return "removed"
        changed = (
            self.start_before != self.start_after
            or self.finish_before != self.finish_after
            or self.cost_before != self.cost_after
        )
        return "changed" if changed else "unchanged"

    @property
    def start_delta_days(self) -> int | None:
        if self.start_before is None or self.start_after is None:
            return None
        return (self.start_after - self.start_before).days

    @property
    def finish_delta_days(self) -> int | None:
        if self.finish_before is None or self.finish_after is None:
            return None
        return (self.finish_after - self.finish_before).days

    @property
    def cost_delta(self) -> float | None:
        if self.cost_before is None or self.cost_after is None:
            return None
        return self.cost_after - self.cost_before


def _sort_key(task_id: str) -> tuple[int, str]:
    """Numeric ids (every real ``task_id`` is ``str(Task.id)``) sort numerically;
    anything else falls back to lexical, after every numeric id."""
    return (0, f"{int(task_id):020d}") if task_id.isdigit() else (1, task_id)


def diff_baseline_lines(
    before: Sequence[BaselineTask], after: Sequence[BaselineTask]
) -> tuple[BaselineLineDiff, ...]:
    """Every task on either baseline, ``before``'s window/cost against ``after``'s,
    ordered by ``task_id`` — deterministic regardless of the order the caller
    loaded the rows in, which is what makes the result a golden value."""
    before_by_id = {task.task_id: task for task in before}
    after_by_id = {task.task_id: task for task in after}
    ids = sorted(set(before_by_id) | set(after_by_id), key=_sort_key)
    diffs = []
    for task_id in ids:
        b, a = before_by_id.get(task_id), after_by_id.get(task_id)
        diffs.append(
            BaselineLineDiff(
                task_id=task_id,
                start_before=b.planned_start if b else None,
                start_after=a.planned_start if a else None,
                finish_before=b.planned_finish if b else None,
                finish_after=a.planned_finish if a else None,
                cost_before=b.planned_cost if b else None,
                cost_after=a.planned_cost if a else None,
            )
        )
    return tuple(diffs)
