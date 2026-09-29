"""Pure evaluation of the balanced-scorecard metric evidence layer.

The evaluator never writes a status back to the store. Given a metric definition,
its observations, and an explicit reporting date, it returns the latest known
reading and a reproducible RAG/coverage result. Missing evidence is ``unknown``;
stale in-tolerance evidence is ``amber``; an out-of-tolerance value is ``red``
even when it is also stale.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from driftless.assess import adapters
from driftless.assess.model import Coverage, RagStatus
from driftless.models import ScorecardMetricDefinition, ScorecardMetricObservation


@dataclass(frozen=True)
class MetricEvaluation:
    """The as-of result for one scorecard metric definition."""

    metric_definition_id: int
    status: RagStatus
    coverage: Coverage
    value: float | None = None
    observed_on: date | None = None


def evaluate_metric(
    definition: ScorecardMetricDefinition,
    observations: Sequence[ScorecardMetricObservation],
    as_of: date,
) -> MetricEvaluation:
    """Classify the latest observation that existed at ``as_of``.

    ``id`` breaks same-day ties deterministically. Rows from the future are
    ignored, keeping historical reports stable when a late observation arrives.
    """

    eligible = [row for row in observations if row.observed_on <= as_of]
    if not eligible:
        return MetricEvaluation(definition.id, "unknown", "missing")

    latest = max(eligible, key=lambda row: (row.observed_on, row.id))
    if definition.direction == "higher_is_better":
        status = _higher_is_better(definition, latest.value)
    else:
        status = _lower_is_better(definition, latest.value)

    stale = (as_of - latest.observed_on).days > definition.cadence_days
    if status == "green" and stale:
        status = "amber"
    coverage: Coverage = "stale" if stale and status != "red" else "measured"
    return MetricEvaluation(definition.id, status, coverage, latest.value, latest.observed_on)


def evaluate_metrics(
    definitions: Sequence[ScorecardMetricDefinition], as_of: date
) -> list[tuple[ScorecardMetricDefinition, MetricEvaluation]]:
    """One row per LOGICAL metric — the dated versions sharing an
    ``(objective_id, name)``, graded through the one
    :func:`adapters.metric_definition_as_of` says is in force at ``as_of``,
    against the UNION of every version's observations: the selected version's
    own set alone would orphan readings posted before it.
    """
    groups: dict[tuple[int, str], list[ScorecardMetricDefinition]] = {}
    for row in definitions:
        groups.setdefault((row.objective_id, row.name), []).append(row)
    graded: list[tuple[ScorecardMetricDefinition, MetricEvaluation]] = []
    for versions in groups.values():
        current = adapters.metric_definition_as_of(versions, as_of)
        if current is None:
            continue
        observations = [obs for version in versions for obs in version.observations]
        graded.append((current, evaluate_metric(current, observations, as_of)))
    return graded


def _higher_is_better(definition: ScorecardMetricDefinition, value: float) -> RagStatus:
    if value >= definition.target_value:
        return "green"
    if value >= definition.amber_threshold:
        return "amber"
    return "red"


def _lower_is_better(definition: ScorecardMetricDefinition, value: float) -> RagStatus:
    if value <= definition.target_value:
        return "green"
    if value <= definition.amber_threshold:
        return "amber"
    return "red"
