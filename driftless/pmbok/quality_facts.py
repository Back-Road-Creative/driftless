"""Adapts ``QualityMetric``/``QualityMeasurement`` rows into ``calc.quality``'s plain
inputs — the same idiom ``driftless.assess.adapters`` uses for earned value, applied to
the quality workbench instead. Pure and as-of aware: every read is filtered to
``measured_on <= as_of`` before it reaches a calculator, and nothing here writes, imports
another ``driftless.calc`` module, or reaches past ``adapters.project_rows`` — which is
what keeps every read inside a project's own ``prefetched`` scope when one is open.

``_out_of_tolerance`` is a second copy of the same test
``assess.evaluators.quality._outside_tolerance`` applies, not an import of it: that
function is private to its module, and reaching across a module boundary for a
leading-underscore name is the same fragility a public one exists to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.calc import quality as calc
from driftless.models import Project, QualityMeasurement


@dataclass(frozen=True)
class MetricSeries:
    """One metric's dated readings, up to and including ``as_of``, plus its control
    chart when there are enough points to estimate one (``calc.control_chart`` needs
    at least two)."""

    name: str
    unit: str | None
    readings: tuple[tuple[date, float], ...]
    chart: calc.ControlChartResult | None


def _out_of_tolerance(row: QualityMeasurement) -> bool:
    """Whether ``row`` fails its linked metric's direction and bounds, or — for a
    legacy row with no linked metric — its own target."""
    metric = row.quality_metric
    if metric is None:
        return row.actual_value > row.target_value
    if metric.direction == "lower_is_better":
        assert metric.upper_bound is not None
        return row.actual_value > metric.upper_bound
    if metric.direction == "higher_is_better":
        assert metric.lower_bound is not None
        return row.actual_value < metric.lower_bound
    assert metric.lower_bound is not None and metric.upper_bound is not None
    return not metric.lower_bound <= row.actual_value <= metric.upper_bound


def _measurements(session: Session, project: Project, as_of: date) -> list[QualityMeasurement]:
    rows = adapters.project_rows(session, QualityMeasurement, project.id)
    return sorted(
        (row for row in rows if row.measured_on <= as_of),
        key=lambda row: (row.metric, row.measured_on, row.id),
    )


def metric_series(session: Session, project: Project, as_of: date) -> list[MetricSeries]:
    """One :class:`MetricSeries` per distinct metric name this project has readings
    for as of ``as_of``, metric name order."""
    by_metric: dict[str, list[QualityMeasurement]] = {}
    for row in _measurements(session, project, as_of):
        by_metric.setdefault(row.metric, []).append(row)
    series: list[MetricSeries] = []
    for name in sorted(by_metric):
        group = by_metric[name]
        readings = tuple((row.measured_on, row.actual_value) for row in group)
        chart = None
        if len(group) >= 2:
            latest = group[-1].quality_metric
            lower = latest.lower_bound if latest is not None else None
            upper = latest.upper_bound if latest is not None else None
            chart = calc.control_chart([row.actual_value for row in group], lower, upper)
        series.append(MetricSeries(name=name, unit=group[-1].unit, readings=readings, chart=chart))
    return series


def failure_pareto(session: Session, project: Project, as_of: date) -> calc.ParetoResult:
    """A Pareto split of out-of-tolerance readings as of ``as_of``, one category per
    metric name — the category a reading fails under is the metric it measures."""
    counts: dict[str, int] = {}
    for row in _measurements(session, project, as_of):
        if _out_of_tolerance(row):
            counts[row.metric] = counts.get(row.metric, 0) + 1
    return calc.pareto(counts)
