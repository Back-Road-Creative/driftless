"""The cost workbench — aggregation, reserves, funding limits, financing and the
cash-flow S-curve. Pure functions over plain value objects, exactly like ``calc.evm``
and ``calc.forecast``: no I/O, no ORM, no wall clock, every entry point takes what it
needs explicitly. Nothing here imports ``driftless.models`` or ``driftless.db`` — the
caller adapts stored rows into the value objects below, the same seam ``calc.evm``
already draws.

``cash_flow_s_curve`` reuses :func:`driftless.calc.evm.planned_value` rather than a
second accrual rule: PV(t) is computed once, in ``calc.evm``, and both the EVM
snapshot and this S-curve read the same number for the same task list and date.

``basis_of_estimate`` renders a plain dict today because ``driftless.calc.estimating``
does not exist yet (checked: no such module in this tree). When it lands with an
``EstimateScenario`` value object, the later hookup should pass its fields through
here rather than duplicating this rendering.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from driftless.calc.evm import BaselineTask, planned_value


@dataclass(frozen=True)
class CostLine:
    """A planned amount for one work package under one control account.

    Mirrors ``driftless.models.records.BudgetLine``'s shape (a planned amount line)
    extended with the work-package/control-account identifiers a WBS rollup needs —
    ``BudgetLine`` itself groups by cost category, not by WBS node. Never the ORM row.
    """

    work_package: str
    control_account: str
    amount: float

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError(f"work package {self.work_package}: amount is negative")


@dataclass(frozen=True)
class CostAggregation:
    """Planned amounts rolled up work package -> control account -> project total."""

    by_work_package: dict[str, float]
    by_control_account: dict[str, float]
    project_total: float


def cost_aggregation(lines: Sequence[CostLine]) -> CostAggregation:
    """Sum ``lines`` at each of the three levels a cost baseline is read at."""
    by_work_package: dict[str, float] = {}
    by_control_account: dict[str, float] = {}
    for line in lines:
        by_work_package[line.work_package] = (
            by_work_package.get(line.work_package, 0.0) + line.amount
        )
        by_control_account[line.control_account] = (
            by_control_account.get(line.control_account, 0.0) + line.amount
        )
    return CostAggregation(
        by_work_package=by_work_package,
        by_control_account=by_control_account,
        project_total=sum(line.amount for line in lines),
    )


@dataclass(frozen=True)
class ReserveAnalysis:
    """PMBOK's two reserves, stated plainly: the **cost baseline** is the work
    packages' cost plus the **contingency reserve** held against known-unknowns
    inside that scope; the **project budget** (``total_budget`` here) is the cost
    baseline plus the **management reserve** held against unknown-unknowns outside
    any single work package's scope, released only under change control."""

    cost_baseline: float
    contingency_reserve: float
    management_reserve: float
    total_budget: float


def reserve_analysis(
    base: float,
    *,
    contingency_pct: float | None = None,
    risk_exposure: float | None = None,
    management_pct: float,
) -> ReserveAnalysis:
    """Determine the cost baseline and total budget from ``base`` (the summed work
    package costs) plus a contingency reserve and a management reserve.

    The contingency reserve is either ``base * contingency_pct`` (a rate applied to
    the work packages' own cost) or the register's own ``risk_exposure`` figure,
    whichever the caller has to hand — exactly one of the two must be given.
    ``management_pct`` is a rate applied to the cost baseline, since PMBOK defines
    the management reserve as a percentage of the baseline it sits on top of, not
    of the raw work package total.
    """
    if base < 0:
        raise ValueError("base is negative")
    if (contingency_pct is None) == (risk_exposure is None):
        raise ValueError("give exactly one of contingency_pct or risk_exposure")
    if contingency_pct is not None:
        if not 0.0 <= contingency_pct <= 1.0:
            raise ValueError("contingency_pct must be between 0 and 1")
        contingency_reserve = base * contingency_pct
    else:
        assert risk_exposure is not None
        if risk_exposure < 0:
            raise ValueError("risk_exposure is negative")
        contingency_reserve = risk_exposure
    if management_pct < 0.0:
        raise ValueError("management_pct must be >= 0")
    cost_baseline = base + contingency_reserve
    management_reserve = cost_baseline * management_pct
    return ReserveAnalysis(
        cost_baseline=cost_baseline,
        contingency_reserve=contingency_reserve,
        management_reserve=management_reserve,
        total_budget=cost_baseline + management_reserve,
    )


@dataclass(frozen=True)
class PeriodAmount:
    """An amount for one named period — NOT cumulative. Used both as a funding
    period's planned spend (fed to ``funding_limit_reconciliation``) and as a
    reported actual (fed to ``run_rate``), since both are "one figure per named
    period" and neither needs a shape the other lacks."""

    period: str
    amount: float

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError(f"period {self.period}: amount is negative")


@dataclass(frozen=True)
class FundingLimitBreach:
    """One period whose cumulative planned spend exceeds its funding limit, and the
    amount that has to shift to a later period to bring it back inside the limit."""

    period: str
    cumulative_planned: float
    limit: float
    excess: float


def funding_limit_reconciliation(
    periods: Sequence[PeriodAmount], limits_by_period: Mapping[str, float]
) -> tuple[FundingLimitBreach, ...]:
    """Cumulative planned spend, period by period in the order ``periods`` is given,
    against ``limits_by_period``. A period absent from ``limits_by_period`` carries
    no limit and can never breach. Reports every breaching period; reconciling the
    schedule to clear a breach — moving which work packages land later — is the
    caller's decision, not this function's."""
    breaches: list[FundingLimitBreach] = []
    running = 0.0
    for period in periods:
        running += period.amount
        limit = limits_by_period.get(period.period)
        if limit is not None and running > limit:
            breaches.append(
                FundingLimitBreach(
                    period=period.period,
                    cumulative_planned=running,
                    limit=limit,
                    excess=running - limit,
                )
            )
    return tuple(breaches)


def financing_cost(
    principal: float, rate: float, periods: float, *, method: str = "simple"
) -> float:
    """Cost of financing ``principal`` at ``rate`` per period over ``periods``.

    ``method="simple"``: ``principal * rate * periods`` — interest on the original
    principal only. ``method="compound"``: ``principal * ((1 + rate) ** periods - 1)``
    — interest on interest, compounding once per period.
    """
    if principal < 0:
        raise ValueError("principal is negative")
    if rate < 0:
        raise ValueError("rate is negative")
    if periods < 0:
        raise ValueError("periods is negative")
    if method == "simple":
        return principal * rate * periods
    if method == "compound":
        return principal * (math.pow(1.0 + rate, periods) - 1.0)
    raise ValueError(f"unknown financing method: {method!r}")


@dataclass(frozen=True)
class SCurvePoint:
    """One sampled date on the cash-flow S-curve and the cumulative planned spend
    the baseline says should have accrued by then."""

    as_of: date
    cumulative_planned: float


def cash_flow_s_curve(
    baseline: Sequence[BaselineTask], as_of: date, samples: int = 12
) -> tuple[SCurvePoint, ...]:
    """Cumulative planned-spend series from the baseline's earliest start through
    ``as_of``, at up to ``samples`` evenly spaced, distinct dates (fewer than
    ``samples`` calendar days in the window samples one point per day instead of
    repeating a date). Each point's figure is exactly
    :func:`driftless.calc.evm.planned_value` at that date — the one accrual rule,
    read here rather than re-derived. Empty ``baseline`` returns no points.
    """
    if not baseline:
        return ()
    if samples < 1:
        raise ValueError("samples must be >= 1")
    start = min(min(task.planned_start for task in baseline), as_of)
    span = max(0, (as_of - start).days)
    dates = dict.fromkeys(
        start + timedelta(days=round(span * i / (samples - 1)) if span else 0)
        for i in range(samples)
    )
    return tuple(SCurvePoint(d, planned_value(baseline, d)) for d in dates)


def run_rate(actuals: Sequence[PeriodAmount], window: int) -> float:
    """Average actual spend per period over the most recent ``window`` periods, in
    the order ``actuals`` is given — the steady-state figure a department or an
    agile team's ongoing budget view reads, as opposed to a one-off snapshot.
    Fewer than ``window`` periods of history uses what exists. No history is 0.0,
    not undefined: a team with zero periods behind it has literally spent nothing
    yet, unlike EVM's ratios, which have no meaningful denominator at all.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    recent = actuals[-window:]
    if not recent:
        return 0.0
    return sum(entry.amount for entry in recent) / len(recent)


def basis_of_estimate(scenario: Mapping[str, object]) -> str:
    """Render a plain-words Basis of Estimate from ``scenario``.

    Recognised keys, all optional: ``method`` (how the figure was produced, e.g.
    "three-point" or "analogous"), ``basis`` (what it was estimated FROM), ``range_low``
    / ``range_high`` (the estimate's spread), ``assumptions`` (a sequence of strings)
    and ``confidence`` (a plain-words confidence statement). A key that is absent is
    omitted from the rendering rather than printed as "unknown" — the basis says what
    it actually knows.

    ``scenario`` is a plain ``Mapping`` rather than an ``EstimateScenario`` because
    ``driftless.calc.estimating`` does not exist in this tree yet; see the module
    docstring.
    """
    lines: list[str] = []
    if "method" in scenario:
        lines.append(f"Estimate method: {scenario['method']}.")
    if "basis" in scenario:
        lines.append(f"Estimated from: {scenario['basis']}.")
    if "range_low" in scenario and "range_high" in scenario:
        lines.append(f"Range: {scenario['range_low']} to {scenario['range_high']}.")
    assumptions = scenario.get("assumptions")
    if isinstance(assumptions, Sequence) and not isinstance(assumptions, str) and assumptions:
        rendered = "; ".join(str(item) for item in assumptions)
        lines.append(f"Assumptions: {rendered}.")
    if "confidence" in scenario:
        lines.append(f"Confidence: {scenario['confidence']}.")
    if not lines:
        return "No basis of estimate recorded."
    return " ".join(lines)
