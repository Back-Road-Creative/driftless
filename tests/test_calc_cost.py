"""Tests for the cost workbench: aggregation, reserves, funding limits, financing
and the cash-flow S-curve. Worked by hand, arithmetic written out."""

from __future__ import annotations

from datetime import date

import pytest

from driftless.calc.cost import (
    CostLine,
    PeriodAmount,
    basis_of_estimate,
    cash_flow_s_curve,
    cost_aggregation,
    financing_cost,
    funding_limit_reconciliation,
    reserve_analysis,
    run_rate,
)
from driftless.calc.evm import BaselineTask, planned_value


def test_cost_aggregation_rolls_up_and_refuses_a_negative_amount() -> None:
    lines = (
        CostLine("WP1", "CA1", 1_000.0),
        CostLine("WP2", "CA1", 500.0),
        CostLine("WP3", "CA2", 2_000.0),
    )
    agg = cost_aggregation(lines)
    assert agg.by_work_package == {"WP1": 1_000.0, "WP2": 500.0, "WP3": 2_000.0}
    assert agg.by_control_account == {"CA1": 1_500.0, "CA2": 2_000.0}
    assert agg.project_total == 3_500.0
    assert cost_aggregation(()).project_total == 0.0
    with pytest.raises(ValueError, match="negative"):
        CostLine("WP1", "CA1", -1.0)


def test_reserve_analysis_worked_examples_and_refusals() -> None:
    # base 100,000; 10% contingency -> baseline 110,000; 5% management -> 5,500 reserve.
    by_rate = reserve_analysis(100_000.0, contingency_pct=0.10, management_pct=0.05)
    assert (by_rate.contingency_reserve, by_rate.cost_baseline) == (10_000.0, 110_000.0)
    assert (by_rate.management_reserve, by_rate.total_budget) == (5_500.0, 115_500.0)
    by_exposure = reserve_analysis(100_000.0, risk_exposure=8_000.0, management_pct=0.10)
    assert by_exposure.cost_baseline == 108_000.0
    assert by_exposure.total_budget == pytest.approx(118_800.0)
    with pytest.raises(ValueError, match="exactly one"):
        reserve_analysis(100.0, management_pct=0.1)
    with pytest.raises(ValueError, match="exactly one"):
        reserve_analysis(100.0, contingency_pct=0.1, risk_exposure=5.0, management_pct=0.1)
    with pytest.raises(ValueError, match="negative"):
        reserve_analysis(-1.0, contingency_pct=0.1, management_pct=0.1)


def test_reserve_analysis_refuses_a_contingency_pct_outside_zero_to_one() -> None:
    with pytest.raises(ValueError, match="contingency_pct must be between 0 and 1"):
        reserve_analysis(100.0, contingency_pct=1.5, management_pct=0.1)


def test_reserve_analysis_refuses_a_negative_risk_exposure() -> None:
    with pytest.raises(ValueError, match="risk_exposure is negative"):
        reserve_analysis(100.0, risk_exposure=-1.0, management_pct=0.1)


def test_reserve_analysis_refuses_a_negative_management_pct() -> None:
    with pytest.raises(ValueError, match="management_pct must be >= 0"):
        reserve_analysis(100.0, contingency_pct=0.1, management_pct=-0.01)


def test_funding_limit_reconciliation_flags_only_the_breaching_periods() -> None:
    periods = (
        PeriodAmount("Q1", 400_000.0),
        PeriodAmount("Q2", 300_000.0),  # cumulative 700,000 > 600,000 limit
        PeriodAmount("Q3", 100_000.0),  # cumulative 800,000, no stated Q3 limit below
    )
    limits = {"Q1": 500_000.0, "Q2": 600_000.0}
    breaches = funding_limit_reconciliation(periods, limits)
    assert [b.period for b in breaches] == ["Q2"]
    assert (breaches[0].cumulative_planned, breaches[0].excess) == (700_000.0, 100_000.0)
    assert funding_limit_reconciliation((PeriodAmount("Q1", 10.0),), {}) == ()
    with pytest.raises(ValueError, match="negative"):
        PeriodAmount("Q1", -1.0)


def test_financing_cost_simple_and_compound_worked_examples_and_refusals() -> None:
    assert financing_cost(10_000.0, 0.05, 3) == 1_500.0  # simple: 10,000 * 0.05 * 3
    # compound: 10,000 * (1.05^3 - 1) = 10,000 * 0.157625 = 1,576.25
    assert financing_cost(10_000.0, 0.05, 3, method="compound") == pytest.approx(1_576.25)
    with pytest.raises(ValueError, match="negative"):
        financing_cost(-1.0, 0.05, 3)
    with pytest.raises(ValueError, match="unknown financing method"):
        financing_cost(10_000.0, 0.05, 3, method="magic")


def test_financing_cost_refuses_a_negative_rate() -> None:
    with pytest.raises(ValueError, match="rate is negative"):
        financing_cost(10_000.0, -0.01, 3)


def test_financing_cost_refuses_a_negative_number_of_periods() -> None:
    with pytest.raises(ValueError, match="periods is negative"):
        financing_cost(10_000.0, 0.05, -1)


BASELINE = (
    BaselineTask("A", date(2026, 1, 1), date(2026, 1, 10), 1_000.0),
    BaselineTask("B", date(2026, 1, 5), date(2026, 1, 24), 4_000.0),
)


def test_s_curve_is_monotonic_matches_the_imported_oracle_and_hits_the_endpoints() -> None:
    points = cash_flow_s_curve(BASELINE, date(2026, 1, 24), samples=8)
    values = [p.cumulative_planned for p in points]
    assert values == sorted(values)
    for point in points:
        assert point.cumulative_planned == planned_value(BASELINE, point.as_of)
    assert points[0].as_of == date(2026, 1, 1)
    assert points[-1].cumulative_planned == 5_000.0  # full BAC by the last planned day
    assert cash_flow_s_curve((), date(2026, 1, 1)) == ()


def test_s_curve_refuses_fewer_than_one_sample() -> None:
    with pytest.raises(ValueError, match="samples must be >= 1"):
        cash_flow_s_curve(BASELINE, date(2026, 1, 24), samples=0)


def test_run_rate_averages_the_trailing_window_and_refuses_a_window_below_one() -> None:
    actuals = (
        PeriodAmount("Jan", 1_000.0),
        PeriodAmount("Feb", 2_000.0),
        PeriodAmount("Mar", 3_000.0),
    )
    assert run_rate(actuals, window=2) == 2_500.0  # (2,000 + 3,000) / 2
    assert run_rate(actuals, window=10) == 2_000.0  # fewer periods than the window exist
    assert run_rate((), window=3) == 0.0
    with pytest.raises(ValueError, match="window"):
        run_rate((PeriodAmount("Jan", 1.0),), window=0)


def test_basis_of_estimate_renders_given_fields_and_the_empty_scenario() -> None:
    text = basis_of_estimate(
        {
            "method": "three-point",
            "basis": "vendor quotes plus historical labor rates",
            "range_low": 90_000.0,
            "range_high": 120_000.0,
            "assumptions": ["rates hold through Q3", "no scope change"],
            "confidence": "medium",
        }
    )
    assert "three-point" in text and "vendor quotes" in text and "medium" in text
    assert "90000.0 to 120000.0" in text
    assert "rates hold through Q3" in text
    assert basis_of_estimate({}) == "No basis of estimate recorded."
