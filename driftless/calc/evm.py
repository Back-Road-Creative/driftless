"""Time-phased earned value — pure functions over plain value objects.

No I/O, no ORM, no wall clock: every entry point takes an explicit ``as_of``,
which makes "generate the report twice, get byte-identical output" testable.
Nothing here imports ``driftless.models``, ``driftless.db`` or another ``driftless.calc``
module — the caller adapts stored rows into the frozen objects below.

**Accrual.** A baseline is a curve, not a total; PV(t) cannot be recovered
from a budget figure alone. Each task accrues its planned cost linearly across
its planned window, counting both endpoint days, with ``as_of`` read as
end-of-day — a task planned 01-10 Jan has accrued a tenth by the end of 01 Jan
and all of it by the end of 10 Jan. Linear is the documented default; a task
needing another shape is split into shorter tasks, not given a private curve.

**Undefined ratios.** Each ratio returns ``None`` on a zero denominator rather
than raising or substituting a number: CPI before the first spend (AC = 0),
SPI before the baseline starts (PV = 0), EAC where nothing is earned (CPI = 0);
ETC and VAC inherit it. A 0.0 or an infinity would poison every rollup above.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BaselineTask:
    """One task's approved plan: when it was to run, and what it was to cost."""

    task_id: str
    planned_start: date
    planned_finish: date
    planned_cost: float

    def __post_init__(self) -> None:
        if self.planned_finish < self.planned_start:
            raise ValueError(f"task {self.task_id}: planned_finish precedes planned_start")
        if self.planned_cost < 0:
            raise ValueError(f"task {self.task_id}: planned_cost is negative")


@dataclass(frozen=True)
class ProgressReport:
    """A dated reading of how far a task had got, as a fraction (not a percent)."""

    task_id: str
    measured_on: date
    percent_complete: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.percent_complete <= 1.0:
            raise ValueError(f"task {self.task_id}: percent_complete must be between 0.0 and 1.0")


@dataclass(frozen=True)
class CostEntry:
    """Money actually spent, carrying the date it was incurred."""

    incurred_on: date
    amount: float


@dataclass(frozen=True)
class EarnedValueSnapshot:
    """Every earned-value figure for one as-of date, computed in one pass."""

    as_of: date
    bac: float
    pv: float
    ev: float
    ac: float
    cpi: float | None
    spi: float | None
    eac: float | None
    etc: float | None
    vac: float | None


def budget_at_completion(baseline: Sequence[BaselineTask]) -> float:
    """BAC — the total approved cost of the baseline."""
    return sum(task.planned_cost for task in baseline)


def _accrued_fraction(task: BaselineTask, as_of: date) -> float:
    """Share of ``task``'s planned window elapsed by the end of ``as_of``."""
    # finish >= start is validated, so the window is >= 1 day and never zero.
    window_days = (task.planned_finish - task.planned_start).days + 1
    elapsed_days = (as_of - task.planned_start).days + 1
    if elapsed_days <= 0:
        return 0.0
    if elapsed_days >= window_days:
        return 1.0
    return elapsed_days / window_days


def planned_value(baseline: Sequence[BaselineTask], as_of: date) -> float:
    """PV — baseline cost the plan says should have accrued by ``as_of``."""
    return sum(task.planned_cost * _accrued_fraction(task, as_of) for task in baseline)


def percent_complete_at(progress: Sequence[ProgressReport], task_id: str, as_of: date) -> float:
    """Latest reading for ``task_id`` dated at or before ``as_of`` (0.0 if none)."""
    reported = [r for r in progress if r.task_id == task_id and r.measured_on <= as_of]
    if not reported:
        return 0.0
    return max(reported, key=lambda report: report.measured_on).percent_complete


def earned_value(
    baseline: Sequence[BaselineTask], progress: Sequence[ProgressReport], as_of: date
) -> float:
    """EV — the sum of (percent complete at ``as_of`` x task baseline cost)."""
    # One pass over ``progress`` replaces a linear rescan per baseline task.
    fraction = _latest_fractions(progress, as_of)
    return sum(task.planned_cost * fraction.get(task.task_id, 0.0) for task in baseline)


def actual_cost(costs: Sequence[CostEntry], as_of: date) -> float:
    """AC — money incurred on or before ``as_of``."""
    return sum(entry.amount for entry in costs if entry.incurred_on <= as_of)


def cost_performance_index(earned: float, actual: float) -> float | None:
    """CPI = EV/AC, or ``None`` before any spend, where efficiency has no meaning."""
    if actual == 0:
        return None
    return earned / actual


def schedule_performance_index(earned: float, planned: float) -> float | None:
    """SPI = EV/PV, or ``None`` before the baseline starts accruing."""
    if planned == 0:
        return None
    return earned / planned


def estimate_at_completion(bac: float, cpi: float | None) -> float | None:
    """EAC = BAC/CPI, or ``None`` while CPI is undefined or still zero."""
    if cpi is None or cpi == 0:
        return None
    return bac / cpi


def estimate_to_complete(eac: float | None, actual: float) -> float | None:
    """ETC = EAC - AC, or ``None`` inherited from an undefined EAC."""
    if eac is None:
        return None
    return eac - actual


def variance_at_completion(bac: float, eac: float | None) -> float | None:
    """VAC = BAC - EAC, or ``None`` inherited from an undefined EAC."""
    if eac is None:
        return None
    return bac - eac


def earned_value_snapshot(
    baseline: Sequence[BaselineTask],
    progress: Sequence[ProgressReport],
    costs: Sequence[CostEntry],
    as_of: date,
) -> EarnedValueSnapshot:
    """Compute the full earned-value set for ``as_of``. Same inputs, same output."""
    bac = budget_at_completion(baseline)
    pv = planned_value(baseline, as_of)
    ev = earned_value(baseline, progress, as_of)
    ac = actual_cost(costs, as_of)
    cpi = cost_performance_index(ev, ac)
    eac = estimate_at_completion(bac, cpi)
    return EarnedValueSnapshot(
        as_of=as_of,
        bac=bac,
        pv=pv,
        ev=ev,
        ac=ac,
        cpi=cpi,
        spi=schedule_performance_index(ev, pv),
        eac=eac,
        etc=estimate_to_complete(eac, ac),
        vac=variance_at_completion(bac, eac),
    )


def _latest_fractions(progress: Sequence[ProgressReport], as_of: date) -> dict[str, float]:
    """Index task_id -> latest fraction dated at or before ``as_of``, in one pass.

    The per-task answer is exactly ``percent_complete_at``'s: readings past
    ``as_of`` are ignored, and a tie on ``measured_on`` keeps the first
    reading seen, as ``max`` breaks ties. Built once per ``earned_value``
    call so EV over N tasks reads N readings once, not N times. Defined at
    the end of the file so the line-pinned citation of
    ``earned_value_snapshot`` in ``docs/pmbok-mapping.md`` stays true.
    """
    latest: dict[str, ProgressReport] = {}
    for report in progress:
        if report.measured_on > as_of:
            continue
        current = latest.get(report.task_id)
        if current is None or report.measured_on > current.measured_on:
            latest[report.task_id] = report
    return {task_id: report.percent_complete for task_id, report in latest.items()}
