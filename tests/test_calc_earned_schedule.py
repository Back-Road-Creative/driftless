"""Tests for earned schedule (Lipke) on top of the EVM core.

The worked example is a two-task project, ten-day planned windows back to
back, BAC = 2,000. Period unit is calendar days from the baseline's earliest
planned start (the module's elapsed-day, end-of-day convention). Every
expected number is hand-computed; the arithmetic is written out in comments.
"""

from __future__ import annotations

from datetime import date

import pytest

from driftless.calc.evm import (
    BaselineTask,
    ProgressReport,
    actual_time,
    earned_schedule,
    earned_schedule_snapshot,
    planned_duration,
)

# A: 01-10 Jan (10-day window, cost 1,000). B: 11-20 Jan (10-day window, cost
# 1,000). BAC = 2,000. Earliest start = 01 Jan, latest finish = 20 Jan, so
# PD = (20 Jan - 01 Jan).days + 1 = 19 + 1 = 20.
BASELINE = (
    BaselineTask("A", date(2026, 1, 1), date(2026, 1, 10), 1000.0),
    BaselineTask("B", date(2026, 1, 11), date(2026, 1, 20), 1000.0),
)


def test_planned_duration_and_actual_time() -> None:
    assert planned_duration(BASELINE) == 20
    # 15 Jan is 14 days after 01 Jan, plus the start day itself -> 15.
    assert actual_time(BASELINE, date(2026, 1, 15)) == 15
    assert actual_time(BASELINE, date(2026, 1, 1)) == 1
    # Empty baseline: nothing to measure against.
    assert planned_duration(()) is None
    assert actual_time((), date(2026, 1, 15)) is None


def test_earned_schedule_interpolates_between_whole_periods() -> None:
    # A reported 100% by 10 Jan; B reported 33% by 15 Jan.
    # EV = 1,000 (A) + 0.33 x 1,000 (B) = 1,330.
    progress = (
        ProgressReport("A", date(2026, 1, 10), 1.0),
        ProgressReport("B", date(2026, 1, 15), 0.33),
    )
    as_of = date(2026, 1, 15)
    # PV curve (elapsed days e, date = 01 Jan + (e-1) days):
    # e=13 -> 13 Jan -> A complete (1,000) + B 3/10 x 1,000 = 300 -> PV=1,300.
    # e=14 -> 14 Jan -> A 1,000 + B 4/10 x 1,000 = 400 -> PV=1,400.
    # EV=1,330 is between: C=13, I = (1,330-1,300)/(1,400-1,300) = 0.3.
    # ES = 13 + 0.3 = 13.3.
    es = earned_schedule(BASELINE, progress, as_of)
    assert es == pytest.approx(13.3)

    snapshot = earned_schedule_snapshot(BASELINE, progress, as_of)
    assert snapshot.es == pytest.approx(13.3)
    assert snapshot.at == 15  # 15 Jan is elapsed day 15
    assert snapshot.pd == 20
    # SPI(t) = ES/AT = 13.3/15 = 0.886666...
    assert snapshot.spi_t == pytest.approx(13.3 / 15)
    # SV(t) = ES - AT = 13.3 - 15 = -1.7
    assert snapshot.sv_t == pytest.approx(-1.7)
    # IEAC(t) = PD/SPI(t) = 20 / (13.3/15) = 20 x 15 / 13.3
    assert snapshot.ieac_t == pytest.approx(20 * 15 / 13.3)


def test_earned_schedule_interpolates_within_the_first_period() -> None:
    # A reported 5% by 05 Jan -> EV = 0.05 x 1,000 = 50.
    # PV curve: e=0 -> 0 (before any accrual); e=1 -> 05 Jan is A's first
    # elapsed day, 1/10 x 1,000 = 100. EV=50 falls between: C=0,
    # I = (50-0)/(100-0) = 0.5 -> ES = 0.5.
    progress = (ProgressReport("A", date(2026, 1, 5), 0.05),)
    es = earned_schedule(BASELINE, progress, date(2026, 1, 5))
    assert es == pytest.approx(0.5)


def test_earned_schedule_zero_progress_is_zero() -> None:
    # No progress reported at all -> EV = 0 -> ES = 0, by definition (EV <= 0
    # returns the start of the curve, not an interpolation).
    snapshot = earned_schedule_snapshot(BASELINE, (), date(2026, 1, 15))
    assert snapshot.es == 0.0
    assert snapshot.at == 15
    assert snapshot.spi_t == pytest.approx(0.0)
    assert snapshot.sv_t == pytest.approx(-15.0)
    # SPI(t) is 0 (not undefined), so IEAC(t) has no finite value -> None.
    assert snapshot.ieac_t is None


def test_earned_schedule_full_progress_equals_planned_duration() -> None:
    # Both tasks 100% complete by 20 Jan -> EV = BAC = 2,000 = PV at 20 Jan,
    # so ES clamps to PD exactly (the "EV >= PV at completion" branch).
    progress = (
        ProgressReport("A", date(2026, 1, 10), 1.0),
        ProgressReport("B", date(2026, 1, 20), 1.0),
    )
    as_of = date(2026, 1, 20)
    snapshot = earned_schedule_snapshot(BASELINE, progress, as_of)
    assert snapshot.es == 20.0
    assert snapshot.pd == 20
    assert snapshot.at == 20
    assert snapshot.spi_t == pytest.approx(1.0)
    assert snapshot.sv_t == pytest.approx(0.0)
    assert snapshot.ieac_t == pytest.approx(20.0)


def test_earned_schedule_at_zero_is_undefined_spi() -> None:
    # 31 Dec 2025 is one day before the baseline's earliest start (01 Jan
    # 2026): AT = (31 Dec - 01 Jan).days + 1 = (-1) + 1 = 0.
    as_of = date(2025, 12, 31)
    snapshot = earned_schedule_snapshot(BASELINE, (), as_of)
    assert snapshot.at == 0
    assert snapshot.es == 0.0
    # SPI(t) = ES/AT is undefined when AT is zero.
    assert snapshot.spi_t is None
    # SV(t) does not depend on AT being nonzero: 0 - 0 = 0.
    assert snapshot.sv_t == pytest.approx(0.0)
    assert snapshot.ieac_t is None


def test_earned_schedule_well_before_start() -> None:
    # 01 Dec 2025 is 31 days before 01 Jan 2026:
    # AT = (01 Dec 2025 - 01 Jan 2026).days + 1 = (-31) + 1 = -30.
    as_of = date(2025, 12, 1)
    snapshot = earned_schedule_snapshot(BASELINE, (), as_of)
    assert snapshot.at == -30
    assert snapshot.es == 0.0
    # AT is nonzero, so SPI(t) is defined: 0 / -30 = 0.0 (not undefined).
    assert snapshot.spi_t == pytest.approx(0.0)
    # SV(t) = 0 - (-30) = 30.
    assert snapshot.sv_t == pytest.approx(30.0)
    # SPI(t) is exactly 0, so IEAC(t) still has no finite value -> None.
    assert snapshot.ieac_t is None


def test_earned_schedule_empty_baseline() -> None:
    snapshot = earned_schedule_snapshot((), (), date(2026, 1, 15))
    assert snapshot.es is None
    assert snapshot.at is None
    assert snapshot.pd is None
    assert snapshot.spi_t is None
    assert snapshot.sv_t is None
    assert snapshot.ieac_t is None
