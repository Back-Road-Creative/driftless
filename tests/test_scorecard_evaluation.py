"""Deterministic evaluation of objective-owned metric evidence."""

from datetime import date

import pytest

from driftless.assess.scorecard import evaluate_metric, evaluate_metrics
from driftless.models import ScorecardMetricDefinition, ScorecardMetricObservation


def _definition(direction: str = "higher_is_better") -> ScorecardMetricDefinition:
    if direction == "higher_is_better":
        return ScorecardMetricDefinition(
            id=7,
            name="Operating margin",
            direction=direction,
            unit="percent",
            target_value=20,
            amber_threshold=15,
            red_threshold=10,
            cadence_days=30,
        )
    return ScorecardMetricDefinition(
        id=7,
        name="Defect rate",
        direction=direction,
        unit="percent",
        target_value=2,
        amber_threshold=4,
        red_threshold=6,
        cadence_days=30,
    )


@pytest.mark.parametrize(
    ("direction", "value", "status"),
    [
        ("higher_is_better", 21, "green"),
        ("higher_is_better", 16, "amber"),
        ("higher_is_better", 9, "red"),
        ("lower_is_better", 1, "green"),
        ("lower_is_better", 3, "amber"),
        ("lower_is_better", 7, "red"),
    ],
)
def test_directional_thresholds_classify_latest_value(
    direction: str, value: float, status: str
) -> None:
    result = evaluate_metric(
        _definition(direction),
        [
            ScorecardMetricObservation(
                id=1,
                metric_definition_id=7,
                observed_on=date(2026, 8, 12),
                value=value,
            )
        ],
        date(2026, 8, 12),
    )

    assert result.status == status
    assert result.coverage == "measured"
    assert result.value == value


def test_missing_and_stale_evidence_are_distinct() -> None:
    definition = _definition()
    missing = evaluate_metric(definition, [], date(2026, 8, 12))
    assert missing.status == "unknown"
    assert missing.coverage == "missing"
    assert missing.observed_on is None

    stale = evaluate_metric(
        definition,
        [
            ScorecardMetricObservation(
                id=1,
                metric_definition_id=7,
                observed_on=date(2026, 7, 1),
                value=21,
            )
        ],
        date(2026, 8, 12),
    )
    assert stale.status == "amber"
    assert stale.coverage == "stale"


def test_evaluate_metrics_skips_a_logical_metric_not_yet_effective() -> None:
    """No version of a logical metric is in force as of ``as_of`` -> excluded entirely,
    rather than graded against a version that has not taken effect yet."""
    not_yet = ScorecardMetricDefinition(
        id=9,
        objective_id=1,
        name="Future metric",
        effective_from=date(2026, 9, 1),  # after as_of below
        observations=[],
        direction="higher_is_better",
        unit="percent",
        target_value=10,
        amber_threshold=5,
        red_threshold=0,
        cadence_days=30,
    )
    assert evaluate_metrics([not_yet], date(2026, 8, 12)) == []


def test_out_of_tolerance_beats_staleness_and_future_rows_are_ignored() -> None:
    result = evaluate_metric(
        _definition(),
        [
            ScorecardMetricObservation(
                id=1,
                metric_definition_id=7,
                observed_on=date(2026, 7, 1),
                value=9,
            ),
            ScorecardMetricObservation(
                id=2,
                metric_definition_id=7,
                observed_on=date(2026, 8, 13),
                value=21,
            ),
        ],
        date(2026, 8, 12),
    )

    assert result.status == "red"
    assert result.coverage == "measured"
    assert result.observed_on == date(2026, 7, 1)


def test_a_metric_with_no_version_in_force_yet_is_skipped_not_graded() -> None:
    """``evaluate_metrics`` groups by ``(objective_id, name)``; a group whose
    every version's ``effective_from`` is after ``as_of`` has none IN FORCE —
    ``adapters.metric_definition_as_of`` answers ``None`` — and is skipped
    rather than graded on a version that does not apply yet. A second,
    already-live metric rides along so the skip is proven against a group
    that DOES get graded, not against an empty result that could pass for
    any reason."""
    live = ScorecardMetricDefinition(
        id=7,
        objective_id=1,
        name="Operating margin",
        direction="higher_is_better",
        unit="percent",
        target_value=20,
        amber_threshold=15,
        red_threshold=10,
        cadence_days=30,
        effective_from=date(2026, 1, 1),
    )
    not_yet_live = ScorecardMetricDefinition(
        id=9,
        objective_id=2,
        name="New KPI",
        direction="higher_is_better",
        unit="percent",
        target_value=20,
        amber_threshold=15,
        red_threshold=10,
        cadence_days=30,
        effective_from=date(2027, 1, 1),
    )
    graded = evaluate_metrics([live, not_yet_live], date(2026, 6, 1))
    assert [definition.id for definition, _ in graded] == [live.id]
