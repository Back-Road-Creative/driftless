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
from datetime import date, timedelta
from enum import Enum


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
    cv: float
    sv: float
    cv_pct: float | None
    sv_pct: float | None


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


def cost_variance(ev: float, ac: float) -> float:
    """CV = EV - AC. Positive is under budget, negative is over budget."""
    return ev - ac


def schedule_variance(ev: float, pv: float) -> float:
    """SV = EV - PV. Positive is ahead of plan, negative is behind plan."""
    return ev - pv


def cost_variance_pct(cv: float, ev: float) -> float | None:
    """CV% = CV/EV, or ``None`` while EV is zero — nothing earned yet to divide by."""
    if ev == 0:
        return None
    return cv / ev


def schedule_variance_pct(sv: float, pv: float) -> float | None:
    """SV% = SV/PV, or ``None`` before the baseline starts accruing."""
    if pv == 0:
        return None
    return sv / pv


class EacMethod(Enum):
    """The standard EAC formulas PMBOK names, one per read of what today's
    variance says about the work still to come.

    ``CPI`` = BAC/CPI: today's cost efficiency holds for the rest of the
    project (the default; the original single-formula behaviour).
    ``REMAINING_AT_PLAN`` = AC + (BAC - EV): today's variance is a one-off, the
    rest runs at the ORIGINAL planned rate. ``REMAINING_AT_CURRENT`` =
    AC + (BAC - EV)/(CPI x SPI): BOTH cost and schedule keep shaping what's
    left. ``BOTTOM_UP`` = AC + a caller-supplied ETC: the team re-estimated the
    remaining work directly and that number is trusted over any formula here.
    """

    CPI = "cpi"
    REMAINING_AT_PLAN = "remaining_at_plan"
    REMAINING_AT_CURRENT = "remaining_at_current"
    BOTTOM_UP = "bottom_up"


def estimate_at_completion(
    bac: float,
    cpi: float | None,
    *,
    method: EacMethod = EacMethod.CPI,
    ev: float | None = None,
    ac: float | None = None,
    spi: float | None = None,
    etc: float | None = None,
) -> float | None:
    """EAC under ``method`` (default :attr:`EacMethod.CPI`, byte-identical to the
    original single-formula ``BAC/CPI``, or ``None`` while CPI is undefined).
    Any other method returns ``None`` — never raises — when the inputs it needs
    are missing, the same policy every ratio here follows.
    """
    if method is EacMethod.CPI:
        if cpi is None or cpi == 0:
            return None
        return bac / cpi
    if method is EacMethod.REMAINING_AT_PLAN:
        if ev is None or ac is None:
            return None
        return ac + (bac - ev)
    if method is EacMethod.REMAINING_AT_CURRENT:
        if ev is None or ac is None or cpi is None or spi is None or cpi == 0 or spi == 0:
            return None
        return ac + (bac - ev) / (cpi * spi)
    if ac is None or etc is None:  # EacMethod.BOTTOM_UP
        return None
    return ac + etc


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


@dataclass(frozen=True)
class TcpiResult:
    """TCPI in its two PMBOK forms: the efficiency the remaining work must run at."""

    to_bac: float | None
    to_eac: float | None


def to_complete_performance_index(
    bac: float, ev: float, ac: float, eac: float | None
) -> TcpiResult:
    """TCPI — the cost efficiency the REMAINING work must hit to land on target.

    ``to_bac`` = (BAC - EV) / (BAC - AC): efficiency needed to still finish at the
    original budget. ``to_eac`` is the same ratio against the CURRENT forecast
    instead — (BAC - EV) / (EAC - AC) — which is always achievable by definition
    (EAC already assumes today's efficiency continues), while ``to_bac`` climbing
    far above 1.0 is the signal the original budget is no longer realistic. Each
    is ``None`` on a zero or undefined denominator, the same policy every other
    ratio here follows.
    """
    to_bac = None if bac == ac else (bac - ev) / (bac - ac)
    to_eac = None if eac is None or eac == ac else (bac - ev) / (eac - ac)
    return TcpiResult(to_bac, to_eac)


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
    cv = cost_variance(ev, ac)
    sv = schedule_variance(ev, pv)
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
        cv=cv,
        sv=sv,
        cv_pct=cost_variance_pct(cv, ev),
        sv_pct=schedule_variance_pct(sv, pv),
    )


def _baseline_window(baseline: Sequence[BaselineTask]) -> tuple[date, date] | None:
    """Earliest planned start and latest planned finish, or ``None`` if empty."""
    if not baseline:
        return None
    return (
        min(task.planned_start for task in baseline),
        max(task.planned_finish for task in baseline),
    )


def planned_duration(baseline: Sequence[BaselineTask]) -> int | None:
    """PD — elapsed days (the same end-of-day convention as ``_accrued_fraction``)
    from the earliest planned start through the latest planned finish, both
    counted. ``None`` for an empty baseline.
    """
    window = _baseline_window(baseline)
    if window is None:
        return None
    start, finish = window
    return (finish - start).days + 1


def actual_time(baseline: Sequence[BaselineTask], as_of: date) -> int | None:
    """AT — elapsed days from the baseline's earliest planned start through
    ``as_of``, in the same convention as :func:`planned_duration`. Zero or
    negative before the baseline starts. ``None`` for an empty baseline.
    """
    window = _baseline_window(baseline)
    if window is None:
        return None
    start, _finish = window
    return (as_of - start).days + 1


def earned_schedule(
    baseline: Sequence[BaselineTask], progress: Sequence[ProgressReport], as_of: date
) -> float | None:
    """ES (Lipke) — the elapsed-day point on the project's own PV curve at
    which cumulative PV equals today's EV, in the same elapsed-day period
    unit as :func:`planned_duration` and :func:`actual_time` (calendar days
    from the baseline's earliest planned start; no separate period model).

    ES = C + I: C is the count of whole elapsed-day periods whose cumulative
    PV is <= EV; I is the fractional position EV reaches into the next
    period, (EV - PV_C) / (PV_{C+1} - PV_C). ``None`` for an empty baseline.
    """
    window = _baseline_window(baseline)
    if window is None:
        return None
    start, _finish = window
    pd = planned_duration(baseline)
    assert pd is not None  # baseline is non-empty, so window and pd both exist
    ev = earned_value(baseline, progress, as_of)

    def pv_at(elapsed_days: int) -> float:
        if elapsed_days <= 0:
            return 0.0
        return planned_value(baseline, start + timedelta(days=elapsed_days - 1))

    # Cumulative PV at completion always equals BAC: every task finishes by
    # its own planned_finish, which is <= the baseline's overall finish.
    if ev <= 0.0:
        return 0.0
    if ev >= pv_at(pd):
        return float(pd)

    period = 0
    while pv_at(period + 1) <= ev:
        period += 1
    lower = pv_at(period)
    upper = pv_at(period + 1)
    fraction = 0.0 if upper == lower else (ev - lower) / (upper - lower)
    return period + fraction


def schedule_performance_index_time(es: float | None, at: int | None) -> float | None:
    """SPI(t) = ES/AT, or ``None`` when either input is undefined or AT is zero."""
    if es is None or at is None or at == 0:
        return None
    return es / at


def schedule_variance_time(es: float | None, at: int | None) -> float | None:
    """SV(t) = ES - AT, or ``None`` when either input is undefined."""
    if es is None or at is None:
        return None
    return es - at


def independent_eac_time(pd: int | None, spi_t: float | None) -> float | None:
    """IEAC(t) = PD/SPI(t), or ``None`` when PD is undefined or SPI(t) is
    undefined or zero (a stalled schedule has no finite time forecast).
    """
    if pd is None or spi_t is None or spi_t == 0:
        return None
    return pd / spi_t


@dataclass(frozen=True)
class EarnedScheduleSnapshot:
    """Every earned-schedule figure for one as-of date, computed in one pass."""

    as_of: date
    es: float | None
    at: int | None
    pd: int | None
    spi_t: float | None
    sv_t: float | None
    ieac_t: float | None


def earned_schedule_snapshot(
    baseline: Sequence[BaselineTask], progress: Sequence[ProgressReport], as_of: date
) -> EarnedScheduleSnapshot:
    """Compute the full earned-schedule set for ``as_of``. Same inputs, same output."""
    pd = planned_duration(baseline)
    at = actual_time(baseline, as_of)
    es = earned_schedule(baseline, progress, as_of)
    spi_t = schedule_performance_index_time(es, at)
    return EarnedScheduleSnapshot(
        as_of=as_of,
        es=es,
        at=at,
        pd=pd,
        spi_t=spi_t,
        sv_t=schedule_variance_time(es, at),
        ieac_t=independent_eac_time(pd, spi_t),
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
