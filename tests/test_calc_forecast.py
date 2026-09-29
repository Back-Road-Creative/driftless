"""Contract tests for `driftless.calc.forecast`.

Written before the module existed. They pin the two things a report can never
get wrong: the band is a pure function of the history handed in, and nothing
reads the wall clock.
"""

import inspect
from datetime import date, timedelta

import pytest

from driftless.calc import forecast as fc

AS_OF = date(2026, 1, 1)


def _history(*points: float) -> list[fc.Sprint]:
    """14-day sprints ending every 14 days, oldest first."""
    return [
        fc.Sprint(
            name=str(i), ended_on=date(2025, 10, 6) + timedelta(days=14 * i), completed_points=p
        )
        for i, p in enumerate(points)
    ]


def test_band_uses_only_the_last_three_sprints() -> None:
    band = fc.forecast_completion(_history(5, 5, 20, 30, 25), remaining_points=90, as_of=AS_OF)
    assert band.sprints_used == 3
    assert (band.velocity_worst, band.velocity_likely, band.velocity_best) == (20.0, 25.0, 30.0)


def test_band_dates_are_exact_and_ordered() -> None:
    band = fc.forecast_completion(_history(20, 30, 25), remaining_points=90, as_of=AS_OF)
    # best 90/30 -> 3 sprints -> 42d; likely 90/25 -> 4 -> 56d; worst 90/20 -> 5 -> 70d
    assert band.best == date(2026, 2, 12)
    assert band.likely == date(2026, 2, 26)
    assert band.worst == date(2026, 3, 12)


def test_short_history_uses_what_exists() -> None:
    band = fc.forecast_completion(_history(20, 30), remaining_points=90, as_of=AS_OF)
    assert band.sprints_used == 2
    assert band.velocity_likely == 25.0


def test_unforecastable_inputs_are_refused() -> None:
    with pytest.raises(ValueError, match="sprint history"):
        fc.forecast_completion([], remaining_points=90, as_of=AS_OF)
    with pytest.raises(ValueError, match="remaining_points"):
        fc.forecast_completion(_history(20), remaining_points=-1, as_of=AS_OF)


def test_a_sprint_refuses_negative_points_or_a_non_positive_length() -> None:
    with pytest.raises(ValueError, match="completed_points >= 0"):
        fc.Sprint(name="Bad", ended_on=AS_OF, completed_points=-1)
    with pytest.raises(ValueError, match="length_days > 0"):
        fc.Sprint(name="Bad", ended_on=AS_OF, completed_points=10, length_days=0)


def test_same_day_ties_at_the_window_boundary_do_not_flip_the_band() -> None:
    """Two sprints sharing ``ended_on`` at the window boundary must not let
    input order decide which one enters the window — otherwise the whole band
    flips with database row order."""
    boundary = date(2025, 11, 3)
    p = fc.Sprint(name="P", ended_on=boundary, completed_points=10)
    q = fc.Sprint(name="Q", ended_on=boundary, completed_points=30)
    later = [
        fc.Sprint(name="R", ended_on=date(2025, 11, 17), completed_points=20),
        fc.Sprint(name="S", ended_on=date(2025, 12, 1), completed_points=20),
    ]
    one = fc.forecast_completion([p, q, *later], remaining_points=90, as_of=AS_OF)
    other = fc.forecast_completion([q, p, *later], remaining_points=90, as_of=AS_OF)
    assert one == other


def test_zero_velocity_never_completes() -> None:
    band = fc.forecast_completion(_history(0, 0, 0), remaining_points=90, as_of=AS_OF)
    assert (band.best, band.likely, band.worst) == (None, None, None)
    assert band.completes is False


def test_partial_zero_velocity_only_drops_the_worst_case() -> None:
    band = fc.forecast_completion(_history(0, 30, 30), remaining_points=90, as_of=AS_OF)
    assert band.worst is None
    assert band.best == date(2026, 2, 12)
    assert band.completes is True


def test_zero_remaining_collapses_the_band_to_as_of() -> None:
    band = fc.forecast_completion(_history(0, 0, 0), remaining_points=0, as_of=AS_OF)
    assert (band.best, band.likely, band.worst) == (AS_OF, AS_OF, AS_OF)
    assert band.completes is True


def test_exposure_is_probability_times_impact() -> None:
    register = [fc.Risk("vendor slip", 0.5, 10_000.0), fc.Risk("scope creep", 0.25, 8_000.0)]
    result = fc.assess_contingency(register, remaining_budget=100_000.0, as_of=AS_OF)
    assert result.exposure == 7_000.0  # 5000 + 2000
    assert result.contingency == 10_000.0  # default 10% of remaining budget
    assert result.covered is True
    assert result.shortfall == 0.0
    assert result.top_risk == "vendor slip"


def test_uncovered_exposure_reports_the_shortfall() -> None:
    register = [fc.Risk("regulatory", 0.8, 50_000.0)]
    result = fc.assess_contingency(
        register, remaining_budget=100_000.0, contingency_rate=0.1, as_of=AS_OF
    )
    assert result.exposure == 40_000.0
    assert result.covered is False
    assert result.shortfall == 30_000.0
    assert result.coverage_ratio == 0.25


def test_empty_register_is_fully_covered() -> None:
    result = fc.assess_contingency([], remaining_budget=100_000.0, as_of=AS_OF)
    assert result.exposure == 0.0
    assert result.covered is True
    assert result.coverage_ratio is None
    assert result.top_risk is None


def test_nonsense_risk_inputs_are_refused() -> None:
    with pytest.raises(ValueError, match="probability"):
        fc.Risk("impossible", 1.5, 100.0)
    with pytest.raises(ValueError, match="remaining_budget"):
        fc.assess_contingency([], remaining_budget=-1.0, as_of=AS_OF)


def test_module_never_reads_the_wall_clock() -> None:
    source = inspect.getsource(fc)
    assert "date.today" not in source
    assert "datetime.now" not in source
