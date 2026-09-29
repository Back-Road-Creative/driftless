"""Golden values for :func:`driftless.calc.baseline_diff.diff_baseline_lines` —
pure, no I/O, so a fixed pair of task lists always produces exactly this diff.
"""

from __future__ import annotations

from datetime import date

from driftless.calc.baseline_diff import BaselineLineDiff, diff_baseline_lines
from driftless.calc.evm import BaselineTask

JAN, FEB = date(2026, 1, 1), date(2026, 2, 1)
JAN_10, FEB_10 = date(2026, 1, 10), date(2026, 2, 10)


def test_changed_added_removed_and_unchanged_lines() -> None:
    before = (
        BaselineTask("1", JAN, JAN_10, 1000.0),  # slips and costs more in v2
        BaselineTask("2", FEB, FEB_10, 500.0),  # dropped in v2
        BaselineTask("3", JAN, JAN_10, 250.0),  # identical in both
    )
    after = (
        BaselineTask("1", JAN_10, FEB, 1500.0),
        BaselineTask("3", JAN, JAN_10, 250.0),
        BaselineTask("4", FEB, FEB_10, 750.0),  # new in v2
    )
    assert diff_baseline_lines(before, after) == (
        BaselineLineDiff("1", JAN, JAN_10, JAN_10, FEB, 1000.0, 1500.0),
        BaselineLineDiff("2", FEB, None, FEB_10, None, 500.0, None),
        BaselineLineDiff("3", JAN, JAN, JAN_10, JAN_10, 250.0, 250.0),
        BaselineLineDiff("4", None, FEB, None, FEB_10, None, 750.0),
    )


def test_status_and_delta_properties() -> None:
    changed, removed, unchanged, added = diff_baseline_lines(
        (
            BaselineTask("1", JAN, JAN_10, 1000.0),
            BaselineTask("2", FEB, FEB_10, 500.0),
            BaselineTask("3", JAN, JAN_10, 250.0),
        ),
        (
            BaselineTask("1", JAN_10, FEB, 1500.0),
            BaselineTask("3", JAN, JAN_10, 250.0),
            BaselineTask("4", FEB, FEB_10, 750.0),
        ),
    )
    assert changed.status == "changed"
    assert changed.start_delta_days == 9
    assert changed.finish_delta_days == 22
    assert changed.cost_delta == 500.0
    assert removed.status == "removed"
    assert removed.start_delta_days is None
    assert removed.cost_delta is None
    assert added.status == "added"
    assert added.finish_delta_days is None
    assert unchanged.status == "unchanged"
    assert unchanged.cost_delta == 0.0


def test_empty_before_and_after_diffs_to_nothing() -> None:
    assert diff_baseline_lines((), ()) == ()


def test_numeric_task_ids_sort_numerically_not_lexically() -> None:
    """ "10" must sort after "2", which a plain string sort would get backwards."""
    before = (BaselineTask("2", JAN, JAN_10, 1.0), BaselineTask("10", JAN, JAN_10, 1.0))
    diffs = diff_baseline_lines(before, before)
    assert [d.task_id for d in diffs] == ["2", "10"]
