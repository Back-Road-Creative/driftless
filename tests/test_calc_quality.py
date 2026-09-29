"""Tests for the quality tools calculator core.

Every expected number is hand-computed, with the arithmetic written out so a
reviewer can check it without running anything.
"""

from __future__ import annotations

import pytest

from driftless.calc.quality import (
    checklist_result,
    control_chart,
    cost_of_quality,
    five_whys,
    pareto,
    root_cause,
    sampling_plan,
)


def test_control_chart_worked_example_flags_an_out_of_control_point() -> None:
    # 12 points at 0, one outlier at 130. mean = (12x0 + 130) / 13 = 10.
    # Deviations: 0 -> -10 (x12, squared 100 each = 1,200); 130 -> 120
    # (squared 14,400). Sum of squares = 15,600; variance (n-1=12) = 1,300;
    # sigma = sqrt(1,300) ~= 36.0555. UCL = 10 + 3 x 36.0555 ~= 118.17.
    measurements = [0.0] * 12 + [130.0]
    result = control_chart(measurements)
    assert result.mean == pytest.approx(10.0)
    assert result.sigma == pytest.approx(36.0555, rel=1e-4)
    assert result.ucl == pytest.approx(118.1664, rel=1e-4)
    assert result.lcl == pytest.approx(-98.1664, rel=1e-4)
    assert result.out_of_control == (12,)  # only the outlier, at index 12
    assert result.out_of_spec == ()  # no spec given
    # The 12 zeros are all below the mean, consecutively -> a rule-of-seven
    # run too, alongside the out-of-control outlier.
    assert result.run_signal is not None
    assert "below the mean" in result.run_signal


def test_control_chart_rule_of_seven_without_an_out_of_control_point() -> None:
    # 3 points at 4, then 7 points at 12. mean = (3x4 + 7x12) / 10 = 9.6.
    # All 7 twelves sit above the mean, consecutively -> a run-of-seven
    # signal, even though every point stays inside +-3sigma.
    measurements = [4.0, 4.0, 4.0, 12.0, 12.0, 12.0, 12.0, 12.0, 12.0, 12.0]
    result = control_chart(measurements)
    assert result.mean == pytest.approx(9.6)
    assert result.out_of_control == ()
    assert result.run_signal is not None
    assert "points 4-10" in result.run_signal
    assert "above the mean" in result.run_signal


def test_control_chart_out_of_spec_is_independent_of_the_control_limits() -> None:
    measurements = [9.0, 10.0, 11.0]
    result = control_chart(measurements, spec_lower=9.5, spec_upper=10.5)
    # Statistically all three are in control (small, symmetric spread), but
    # index 0 (9.0) and index 2 (11.0) both fall outside the 9.5-10.5 spec.
    assert result.out_of_control == ()
    assert result.out_of_spec == (0, 2)


def test_control_chart_needs_at_least_two_points() -> None:
    with pytest.raises(ValueError, match="at least 2 measurements"):
        control_chart([5.0])


def test_control_chart_all_equal_has_zero_spread_and_no_signals() -> None:
    result = control_chart([7.0, 7.0, 7.0, 7.0])
    assert result.sigma == 0.0
    assert result.ucl == result.mean == result.lcl == 7.0
    assert result.out_of_control == ()
    assert result.run_signal is None


def test_pareto_worked_example_cuts_the_vital_few_at_eighty_percent() -> None:
    # Total = 100. Cumulative shares: seals 50 -> 50%, paint 25 -> 75%,
    # hinges 15 -> 90%, trim 10 -> 100%. The vital few are the categories
    # needed to *reach* 80%: seals, paint, and hinges (which crosses 80%).
    counts = {"seals": 50, "paint": 25, "hinges": 15, "trim": 10}
    result = pareto(counts)
    assert [e.category for e in result.entries] == ["seals", "paint", "hinges", "trim"]
    assert result.entries[0].share == pytest.approx(0.5)
    assert result.entries[1].cumulative_share == pytest.approx(0.75)
    assert result.entries[2].cumulative_share == pytest.approx(0.9)
    assert result.entries[3].cumulative_share == pytest.approx(1.0)
    assert result.vital_few == ("seals", "paint", "hinges")


def test_pareto_of_empty_counts_is_empty_not_a_division_error() -> None:
    result = pareto({})
    assert result.entries == ()
    assert result.vital_few == ()


def test_pareto_of_all_zero_counts_is_also_empty() -> None:
    result = pareto({"a": 0, "b": 0})
    assert result.entries == ()
    assert result.vital_few == ()


def test_sampling_plan_worked_example() -> None:
    # z(95%) = 1.96. n0 = 1.96^2 x 0.25 / 0.05^2 = 0.9604 / 0.0025 = 384.16.
    # n = 384.16 / (1 + 383.16 / 1000) = 384.16 / 1.38316 ~= 277.7 -> 278.
    result = sampling_plan(population=1000, confidence=0.95, margin=0.05)
    assert result.sample_size == 278
    assert "z=1.96" in result.formula


def test_sampling_plan_caps_at_the_population() -> None:
    result = sampling_plan(population=10, confidence=0.95, margin=0.01)
    assert result.sample_size == 10


def test_sampling_plan_rejects_an_unlisted_confidence() -> None:
    with pytest.raises(ValueError, match="confidence must be one of"):
        sampling_plan(population=100, confidence=0.5, margin=0.05)


def test_sampling_plan_rejects_a_margin_outside_zero_and_one() -> None:
    with pytest.raises(ValueError, match="margin must be between 0 and 1"):
        sampling_plan(population=100, confidence=0.95, margin=1.5)


def test_cost_of_quality_worked_example_failure_costs_dominate() -> None:
    result = cost_of_quality(
        prevention=1000.0, appraisal=500.0, internal_failure=2000.0, external_failure=3000.0
    )
    assert result.conformance == 1500.0
    assert result.nonconformance == 5000.0
    assert result.total == 6500.0
    assert result.conformance_share == pytest.approx(1500.0 / 6500.0)
    assert "Failure costs exceed" in result.interpretation


def test_cost_of_quality_prevention_side_dominates() -> None:
    result = cost_of_quality(
        prevention=4000.0, appraisal=1000.0, internal_failure=500.0, external_failure=500.0
    )
    assert "front-loaded" in result.interpretation


def test_cost_of_quality_all_zero_has_no_share() -> None:
    result = cost_of_quality(0.0, 0.0, 0.0, 0.0)
    assert result.total == 0.0
    assert result.conformance_share is None
    assert "No quality cost recorded" in result.interpretation


def test_cost_of_quality_rejects_a_negative_input() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        cost_of_quality(-1.0, 0.0, 0.0, 0.0)


def test_root_cause_builds_a_fishbone_shape() -> None:
    diagram = root_cause(
        "window leaks after install",
        {"method": ("no flashing check",), "material": ("substituted sealant",)},
    )
    assert diagram.effect == "window leaks after install"
    assert diagram.categories[0].category == "method"
    assert diagram.categories[0].causes == ("no flashing check",)
    assert diagram.categories[1].causes == ("substituted sealant",)


def test_five_whys_names_the_last_answer_as_the_root_cause() -> None:
    chain = five_whys(("rushed", "behind schedule", "no checklist step"))
    assert chain.chain == ("rushed", "behind schedule", "no checklist step")
    assert chain.root_cause == "no checklist step"


def test_five_whys_rejects_an_empty_chain() -> None:
    with pytest.raises(ValueError, match="at least one answer"):
        five_whys(())


def test_checklist_result_names_the_failing_items() -> None:
    result = checklist_result({"footings inspected": True, "moisture check": False})
    assert result.passed is False
    assert result.failing == ("moisture check",)


def test_checklist_result_passes_when_every_item_passes() -> None:
    result = checklist_result({"a": True, "b": True})
    assert result.passed is True
    assert result.failing == ()


def test_checklist_result_of_an_empty_checklist_passes_vacuously() -> None:
    result = checklist_result({})
    assert result.passed is True
    assert result.failing == ()


def test_quality_tools_are_deterministic() -> None:
    measurements = [4.0, 4.0, 4.0, 12.0, 12.0, 12.0, 12.0, 12.0, 12.0, 12.0]
    assert control_chart(measurements) == control_chart(measurements)
    counts = {"a": 5, "b": 3}
    assert pareto(counts) == pareto(counts)
