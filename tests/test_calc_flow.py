"""Tests for the flow-metrics calculator core.

Written before the module existed, alongside ``calc/flow.py``. They pin
totality over the edge cases the docstrings promise (empty, all done, none
started, as-of before creation, done-after-as-of does not count) plus
determinism and that ``release_forecast`` is the same oracle as
``forecast_completion``, not a restated one.
"""

from __future__ import annotations

from datetime import date

import pytest

from driftless.calc import flow
from driftless.calc.forecast import Sprint, forecast_completion

AS_OF = date(2026, 1, 20)


def _item(
    id_: str,
    created: date,
    started: date | None = None,
    done: date | None = None,
    points: float = 1.0,
) -> flow.WorkItem:
    return flow.WorkItem(
        id=id_, created_on=created, started_on=started, done_on=done, points=points
    )


ITEMS = (
    _item("A", date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 10), points=3.0),
    _item("B", date(2026, 1, 3), date(2026, 1, 5), None, points=2.0),
    _item("C", date(2026, 1, 8), None, None, points=1.0),
    _item("D", date(2026, 1, 4), date(2026, 1, 6), date(2026, 1, 9), points=5.0),
)


def test_work_item_rejects_impossible_orderings() -> None:
    with pytest.raises(ValueError, match="started_on precedes created_on"):
        flow.WorkItem("X", date(2026, 1, 5), date(2026, 1, 4), None, 1.0)
    with pytest.raises(ValueError, match="done_on precedes created_on"):
        flow.WorkItem("X", date(2026, 1, 5), None, date(2026, 1, 4), 1.0)
    with pytest.raises(ValueError, match="done_on precedes started_on"):
        flow.WorkItem("X", date(2026, 1, 1), date(2026, 1, 5), date(2026, 1, 4), 1.0)
    with pytest.raises(ValueError, match="points is negative"):
        flow.WorkItem("X", date(2026, 1, 1), None, None, -1.0)


class TestWip:
    def test_counts_started_items_not_yet_done(self) -> None:
        # B started 1/5, never done, so it is still WIP on 1/10; A and D finished by then.
        assert flow.wip(ITEMS, date(2026, 1, 10)) == 1
        assert flow.wip(ITEMS, date(2026, 1, 7)) == 3  # A, B, D all started, none done by then

    def test_empty_is_zero(self) -> None:
        assert flow.wip((), AS_OF) == 0

    def test_none_started_is_zero(self) -> None:
        never_started = (_item("A", date(2026, 1, 1)),)
        assert flow.wip(never_started, AS_OF) == 0

    def test_as_of_before_creation_is_zero(self) -> None:
        assert flow.wip(ITEMS, date(2025, 12, 1)) == 0


class TestThroughput:
    def test_counts_finished_in_window(self) -> None:
        assert flow.throughput(ITEMS, date(2026, 1, 1), date(2026, 1, 10)) == 2  # A, D

    def test_done_after_as_of_does_not_count(self) -> None:
        assert flow.throughput(ITEMS, date(2026, 1, 1), date(2026, 1, 9)) == 1  # D only

    def test_empty_is_zero(self) -> None:
        assert flow.throughput((), date(2026, 1, 1), AS_OF) == 0

    def test_inverted_window_is_refused(self) -> None:
        with pytest.raises(ValueError, match="window_start"):
            flow.throughput(ITEMS, date(2026, 1, 10), date(2026, 1, 1))


class TestCycleAndLeadTime:
    def test_cycle_time_only_counts_started_and_done(self) -> None:
        # A: 1/2 -> 1/10 = 8 days. D: 1/6 -> 1/9 = 3 days. B, C excluded.
        # Nearest-rank over the sorted [3, 8]: median (rank 0) is 3, p85 (rank 1) is 8.
        stats = flow.cycle_time(ITEMS, AS_OF)
        assert stats.count == 2
        assert stats.median == pytest.approx(3.0)
        assert stats.p85 == pytest.approx(8.0)

    def test_lead_time_counts_every_done_item_regardless_of_start(self) -> None:
        # A: 1/1 -> 1/10 = 9 days. D: 1/4 -> 1/9 = 5 days. Nearest-rank median of [5, 9] is 5.
        stats = flow.lead_time(ITEMS, AS_OF)
        assert stats.count == 2
        assert stats.median == pytest.approx(5.0)

    def test_done_after_as_of_excluded(self) -> None:
        stats = flow.cycle_time(ITEMS, date(2026, 1, 5))
        assert stats.count == 0
        assert stats.median is None
        assert stats.p85 is None

    def test_empty_items_yield_no_stats(self) -> None:
        stats = flow.lead_time((), AS_OF)
        assert (stats.count, stats.median, stats.p85) == (0, None, None)

    def test_none_started_never_counts_toward_cycle_time(self) -> None:
        only_created = (_item("A", date(2026, 1, 1), done=date(2026, 1, 5)),)
        assert flow.cycle_time(only_created, AS_OF).count == 0
        assert flow.lead_time(only_created, AS_OF).count == 1


class TestBurndownAndBurnup:
    def test_burndown_reaches_zero_once_everything_finishes(self) -> None:
        all_done = (
            _item("A", date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 3), points=4.0),
            _item("B", date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 2), points=6.0),
        )
        series = flow.burndown(all_done, date(2026, 1, 1), date(2026, 1, 5), AS_OF)
        assert [p.remaining_points for p in series] == [10.0, 4.0, 0.0, 0.0, 0.0]

    def test_burndown_stops_at_as_of_not_iteration_end(self) -> None:
        series = flow.burndown(ITEMS, date(2026, 1, 1), date(2026, 2, 1), date(2026, 1, 3))
        assert len(series) == 3
        assert series[-1].day == date(2026, 1, 3)

    def test_burndown_as_of_before_iteration_is_empty(self) -> None:
        assert flow.burndown(ITEMS, date(2026, 2, 1), date(2026, 2, 10), AS_OF) == []

    def test_burndown_rejects_inverted_window(self) -> None:
        with pytest.raises(ValueError, match="iteration_end"):
            flow.burndown(ITEMS, date(2026, 1, 10), date(2026, 1, 1), AS_OF)

    def test_burndown_empty_items_is_flat_zero(self) -> None:
        series = flow.burndown((), date(2026, 1, 1), date(2026, 1, 2), AS_OF)
        assert [p.remaining_points for p in series] == [0.0, 0.0]

    def test_burnup_scope_grows_as_items_are_created(self) -> None:
        series = flow.burnup(ITEMS, date(2026, 1, 1), date(2026, 1, 10), AS_OF)
        by_day = {p.day: p for p in series}
        assert by_day[date(2026, 1, 1)].scope_points == 3.0  # only A exists
        assert by_day[date(2026, 1, 10)].scope_points == 11.0  # all four exist
        assert by_day[date(2026, 1, 10)].completed_points == 8.0  # A + D done

    def test_burnup_empty_items_is_flat_zero(self) -> None:
        series = flow.burnup((), date(2026, 1, 1), date(2026, 1, 2), AS_OF)
        assert all(p.completed_points == 0.0 and p.scope_points == 0.0 for p in series)


class TestCumulativeFlow:
    def test_counts_split_across_the_three_states(self) -> None:
        series = flow.cumulative_flow(ITEMS, date(2026, 1, 1), date(2026, 1, 10))
        by_day = {p.day: p for p in series}
        day7 = by_day[date(2026, 1, 7)]
        # C is not yet created on 1/7 (created 1/8) so it is not counted anywhere that day.
        assert (day7.not_started, day7.in_progress, day7.done) == (0, 3, 0)  # A,B,D in progress
        day10 = by_day[date(2026, 1, 10)]
        assert (day10.not_started, day10.in_progress, day10.done) == (1, 1, 2)  # C; B; A,D

    def test_item_not_yet_created_is_not_counted_anywhere(self) -> None:
        series = flow.cumulative_flow(ITEMS, date(2025, 12, 30), date(2025, 12, 31))
        for point in series:
            assert (point.not_started, point.in_progress, point.done) == (0, 0, 0)

    def test_as_of_before_start_is_empty(self) -> None:
        assert flow.cumulative_flow(ITEMS, date(2026, 2, 1), date(2026, 1, 1)) == []

    def test_empty_items_is_all_zero(self) -> None:
        series = flow.cumulative_flow((), date(2026, 1, 1), date(2026, 1, 2))
        assert all((p.not_started, p.in_progress, p.done) == (0, 0, 0) for p in series)


def _history() -> list[Sprint]:
    return [
        Sprint(name="1", ended_on=date(2025, 12, 8), completed_points=20.0),
        Sprint(name="2", ended_on=date(2025, 12, 22), completed_points=30.0),
        Sprint(name="3", ended_on=date(2026, 1, 5), completed_points=25.0),
    ]


def test_release_forecast_agrees_with_forecast_completion() -> None:
    history = _history()
    remaining = 90.0
    as_of = date(2026, 1, 20)
    assert flow.release_forecast(history, remaining, as_of) == forecast_completion(
        history, remaining, as_of
    )


def test_flow_functions_are_deterministic() -> None:
    assert flow.wip(ITEMS, AS_OF) == flow.wip(ITEMS, AS_OF)
    assert flow.cycle_time(ITEMS, AS_OF) == flow.cycle_time(ITEMS, AS_OF)
    assert flow.cumulative_flow(ITEMS, date(2026, 1, 1), AS_OF) == flow.cumulative_flow(
        ITEMS, date(2026, 1, 1), AS_OF
    )
