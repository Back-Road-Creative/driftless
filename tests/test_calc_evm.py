"""Tests for the time-phased earned-value core.

The worked example is a four-task project, every task a ten-day planned
window, BAC = 10,000. Every expected number is hand-computed, with the
arithmetic written out so a reviewer can check it without running anything.
"""

from __future__ import annotations

from datetime import date

import pytest

from driftless.calc.evm import (
    BaselineTask,
    CostEntry,
    EacMethod,
    ProgressReport,
    earned_value_snapshot,
    estimate_at_completion,
    planned_value,
    to_complete_performance_index,
)

# Baseline — task, planned window (inclusive), planned cost; BAC = 10,000.
BASELINE = (
    BaselineTask("A", date(2026, 1, 1), date(2026, 1, 10), 1000.0),
    BaselineTask("B", date(2026, 1, 5), date(2026, 1, 14), 2000.0),
    BaselineTask("C", date(2026, 1, 11), date(2026, 1, 20), 3000.0),
    BaselineTask("D", date(2026, 1, 15), date(2026, 1, 24), 4000.0),
)

# A's 50% is superseded; B's 60% postdates the report date. Both ignored below.
PROGRESS = (
    ProgressReport("A", date(2026, 1, 6), 0.5),
    ProgressReport("A", date(2026, 1, 10), 1.0),
    ProgressReport("B", date(2026, 1, 10), 0.4),
    ProgressReport("B", date(2026, 1, 12), 0.6),
)

COSTS = (
    CostEntry(date(2026, 1, 3), 500.0),
    CostEntry(date(2026, 1, 8), 1500.0),
    CostEntry(date(2026, 1, 12), 900.0),
)

AS_OF = date(2026, 1, 10)


def test_planned_value_accrues_partially_across_a_window() -> None:
    # End of 05 Jan. A: 5 of its 10 days -> 0.5 x 1,000 = 500.
    # B: 1 of its 10 days -> 0.1 x 2,000 = 200. C and D have not started.
    # PV = 700, which is not an endpoint of any task's curve.
    assert planned_value(BASELINE, date(2026, 1, 5)) == 700.0


def test_planned_value_at_the_curve_endpoints() -> None:
    assert planned_value(BASELINE, date(2025, 12, 31)) == 0.0
    assert planned_value(BASELINE, date(2026, 1, 24)) == 10_000.0
    # A one-day task divides by a window of 1, not 0, and accrues in full.
    milestone = (BaselineTask("M", date(2026, 1, 5), date(2026, 1, 5), 500.0),)
    assert planned_value(milestone, date(2026, 1, 4)) == 0.0
    assert planned_value(milestone, date(2026, 1, 5)) == 500.0


def test_worked_example_snapshot() -> None:
    snapshot = earned_value_snapshot(BASELINE, PROGRESS, COSTS, AS_OF)
    assert snapshot.bac == 10_000.0  # 1,000 + 2,000 + 3,000 + 4,000
    assert snapshot.pv == 2_200.0  # A 10/10 x 1,000 + B 6/10 x 2,000; C, D unstarted
    assert snapshot.ev == 1_800.0  # A 100% x 1,000 + B 40% x 2,000; C, D unreported
    assert snapshot.ac == 2_000.0  # 500 (03 Jan) + 1,500 (08 Jan); 900 is dated 12 Jan
    assert snapshot.cpi == pytest.approx(0.9)  # EV/AC = 1,800 / 2,000
    assert snapshot.spi == pytest.approx(0.818181, rel=1e-5)  # EV/PV = 1,800 / 2,200
    assert snapshot.eac == pytest.approx(11_111.111111)  # BAC/CPI = 10,000 / 0.9
    assert snapshot.etc == pytest.approx(9_111.111111)  # EAC - AC = 11,111.11 - 2,000
    assert snapshot.vac == pytest.approx(-1_111.111111)  # BAC - EAC = 10,000 - 11,111.11
    assert snapshot.cv == pytest.approx(-200.0)  # EV - AC = 1,800 - 2,000
    assert snapshot.sv == pytest.approx(-400.0)  # EV - PV = 1,800 - 2,200
    assert snapshot.cv_pct == pytest.approx(-0.111111, rel=1e-5)  # CV/EV = -200 / 1,800
    assert snapshot.sv_pct == pytest.approx(-0.181818, rel=1e-5)  # SV/PV = -400 / 2,200
    # Before anything is earned or planned, CV/SV still compute (both 0.0 - 0.0 = 0), but
    # dividing them by EV/PV = 0 is undefined, same policy as every other ratio here.
    empty = earned_value_snapshot(BASELINE, (), (), date(2025, 12, 31))
    assert empty.cv == 0.0 and empty.cv_pct is None and empty.sv_pct is None


def test_eac_methods_off_the_worked_example_and_their_missing_inputs() -> None:
    # Default is CPI, byte-identical to the original single-formula behaviour.
    assert estimate_at_completion(10_000.0, 0.9) == pytest.approx(11_111.111111)
    assert estimate_at_completion(10_000.0, 0.9) == estimate_at_completion(
        10_000.0, 0.9, method=EacMethod.CPI
    )
    # AC + (BAC - EV) = 2,000 + (10,000 - 1,800)
    assert estimate_at_completion(
        10_000.0, 0.9, method=EacMethod.REMAINING_AT_PLAN, ev=1_800.0, ac=2_000.0
    ) == pytest.approx(10_200.0)
    assert estimate_at_completion(10_000.0, 0.9, method=EacMethod.REMAINING_AT_PLAN) is None
    # AC + (BAC - EV) / (CPI x SPI) = 2,000 + 8,200 / (0.9 x 0.818181...)
    assert estimate_at_completion(
        10_000.0,
        0.9,
        method=EacMethod.REMAINING_AT_CURRENT,
        ev=1_800.0,
        ac=2_000.0,
        spi=0.818181818,
    ) == pytest.approx(13_135.802469, rel=1e-5)
    assert (
        estimate_at_completion(
            10_000.0, 0.9, method=EacMethod.REMAINING_AT_CURRENT, ev=1_800.0, ac=2_000.0
        )
        is None
    )  # spi missing
    assert estimate_at_completion(  # bottom-up trusts the caller's ETC outright
        10_000.0, 0.9, method=EacMethod.BOTTOM_UP, ac=2_000.0, etc=5_000.0
    ) == pytest.approx(7_000.0)
    assert estimate_at_completion(10_000.0, 0.9, method=EacMethod.BOTTOM_UP, ac=2_000.0) is None


def test_snapshot_is_deterministic_for_the_same_as_of() -> None:
    assert earned_value_snapshot(BASELINE, PROGRESS, COSTS, AS_OF) == earned_value_snapshot(
        BASELINE, PROGRESS, COSTS, AS_OF
    )


def test_cost_indices_are_undefined_before_any_spend() -> None:
    # 02 Jan: nothing incurred yet, so AC = 0. CPI and everything derived from
    # it is undefined rather than a ZeroDivisionError or a misleading zero.
    snapshot = earned_value_snapshot(BASELINE, PROGRESS, COSTS, date(2026, 1, 2))
    assert snapshot.ac == 0.0
    assert snapshot.cpi is None
    assert snapshot.eac is None
    assert snapshot.etc is None
    assert snapshot.vac is None


def test_spi_is_undefined_before_the_baseline_starts() -> None:
    snapshot = earned_value_snapshot(BASELINE, PROGRESS, COSTS, date(2025, 12, 31))
    assert snapshot.pv == 0.0
    assert snapshot.spi is None


def test_eac_is_undefined_when_nothing_has_been_earned() -> None:
    # Money spent, no progress reported: CPI = 0/500 = 0.0, so BAC/CPI would
    # divide by zero. EAC is undefined and ETC and VAC inherit that.
    snapshot = earned_value_snapshot(BASELINE, (), COSTS[:1], date(2026, 1, 3))
    assert snapshot.cpi == 0.0
    assert snapshot.eac is None
    assert snapshot.etc is None
    assert snapshot.vac is None


def test_tcpi_both_forms_off_the_worked_example() -> None:
    snapshot = earned_value_snapshot(BASELINE, PROGRESS, COSTS, AS_OF)
    tcpi = to_complete_performance_index(snapshot.bac, snapshot.ev, snapshot.ac, snapshot.eac)
    # to_bac = (10,000 - 1,800) / (10,000 - 2,000) = 8,200 / 8,000
    assert tcpi.to_bac == pytest.approx(1.025)
    # to_eac = (10,000 - 1,800) / (11,111.11 - 2,000) = 8,200 / 9,111.11
    assert tcpi.to_eac == pytest.approx(0.9, rel=1e-4)


def test_tcpi_is_undefined_on_a_zero_denominator() -> None:
    # Fully spent to the original budget: to_bac would divide by zero.
    tcpi = to_complete_performance_index(1000.0, 500.0, 1000.0, 2000.0)
    assert tcpi.to_bac is None
    assert tcpi.to_eac == pytest.approx(0.5)
    # No EAC at all: to_eac inherits the undefined forecast.
    tcpi_no_eac = to_complete_performance_index(1000.0, 500.0, 500.0, None)
    assert tcpi_no_eac.to_eac is None
    assert tcpi_no_eac.to_bac == pytest.approx(1.0)


def test_value_objects_reject_impossible_inputs() -> None:
    with pytest.raises(ValueError, match="precedes"):
        BaselineTask("X", date(2026, 1, 10), date(2026, 1, 1), 100.0)
    with pytest.raises(ValueError, match="negative"):
        BaselineTask("X", date(2026, 1, 1), date(2026, 1, 10), -1.0)
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        ProgressReport("X", date(2026, 1, 1), 1.5)
