"""One fixture per DCMA check that fails it and one that passes it."""

from __future__ import annotations

from datetime import date

from driftless.calc.dcma import (
    assess,
    assess_full,
    check_bei,
    check_critical_path_test,
    check_cpli,
    check_hard_constraints,
    check_high_duration,
    check_high_float,
    check_invalid_dates,
    check_leads,
    check_lags,
    check_logic,
    check_missed_tasks,
    check_negative_float,
    check_relationship_types,
    check_resources,
)
from driftless.calc.network import (
    Activity,
    Dependency,
    ScheduleNetwork,
    backward_pass,
    forward_pass,
    total_float,
)

AS_OF = date(2026, 6, 1)

CONNECTED = ScheduleNetwork(
    activities=(Activity("A", 1), Activity("B", 1), Activity("C", 1)),
    dependencies=(Dependency("A", "B", "FS"), Dependency("B", "C", "FS")),
)
ISOLATED = ScheduleNetwork(
    activities=(Activity("A", 1), Activity("B", 1), Activity("X", 1)),
    dependencies=(Dependency("A", "B", "FS"),),
)
LEAD = ScheduleNetwork(
    activities=(Activity("A", 3), Activity("B", 2)),
    dependencies=(Dependency("A", "B", "FS", lag=-1),),
)
LAGGY = ScheduleNetwork(
    activities=(Activity("A", 3), Activity("B", 2), Activity("C", 2)),
    dependencies=(Dependency("A", "B", "FS", lag=5), Dependency("A", "C", "FS")),
)
MIXED_KINDS = ScheduleNetwork(
    activities=(Activity("A", 3), Activity("B", 2), Activity("C", 2)),
    dependencies=(Dependency("A", "B", "FS"), Dependency("A", "C", "SS")),
)
UNBALANCED_FLOAT = ScheduleNetwork(
    activities=(Activity("A", 1), Activity("B", 1), Activity("C", 50)),
    dependencies=(Dependency("A", "B", "FS"), Dependency("A", "C", "FS")),
)
BALANCED_FLOAT = ScheduleNetwork(
    activities=(Activity("A", 1), Activity("B", 1), Activity("C", 1)),
    dependencies=(Dependency("A", "B", "FS"), Dependency("A", "C", "FS")),
)


def _floats(network: ScheduleNetwork) -> dict[str, int]:
    early = forward_pass(network)
    return total_float(early, backward_pass(network, early))


def test_check_logic_fail_and_pass() -> None:
    assert check_logic(ISOLATED).passed is False
    assert check_logic(ISOLATED).offending_ids == ("X",)
    assert check_logic(CONNECTED).passed is True


def test_check_leads_fail_and_pass() -> None:
    assert check_leads(LEAD).passed is False
    assert check_leads(LEAD).offending_ids == ("A", "B")
    assert check_leads(CONNECTED).passed is True


def test_check_lags_fail_and_pass() -> None:
    assert check_lags(LAGGY).passed is False
    assert check_lags(LAGGY).offending_ids == ("A", "B")
    assert check_lags(CONNECTED).passed is True


def test_check_relationship_types_fail_and_pass() -> None:
    assert check_relationship_types(MIXED_KINDS).passed is False
    assert check_relationship_types(MIXED_KINDS).offending_ids == ("A", "C")
    result = check_relationship_types(CONNECTED)
    assert result.passed is True
    assert result.ratio == 1.0


def test_check_hard_constraints_is_never_assessable() -> None:
    result = check_hard_constraints(CONNECTED)
    assert result.assessable is False
    assert "not assessable" in result.note


def test_check_high_float_fail_and_pass() -> None:
    fail = check_high_float(UNBALANCED_FLOAT, _floats(UNBALANCED_FLOAT))
    assert fail.passed is False
    assert fail.offending_ids == ("B",)
    ok = check_high_float(BALANCED_FLOAT, _floats(BALANCED_FLOAT))
    assert ok.passed is True
    assert ok.numerator == 0


def test_check_negative_float_fail_and_pass() -> None:
    # network.py's own backward_pass can never produce a negative total
    # float (see the module docstring), so the failing fixture injects a
    # floats mapping directly rather than deriving one.
    fail = check_negative_float(CONNECTED, {"A": 0, "B": -1, "C": 0})
    assert fail.passed is False
    assert fail.offending_ids == ("B",)
    ok = check_negative_float(CONNECTED, _floats(CONNECTED))
    assert ok.passed is True
    assert ok.numerator == 0


def test_assess_returns_all_seven_checks_in_order() -> None:
    results = assess(CONNECTED)
    assert [r.name for r in results] == [
        "logic",
        "leads",
        "lags",
        "relationship_types",
        "hard_constraints",
        "high_float",
        "negative_float",
    ]
    assert all(r.passed for r in results)


def test_check_high_duration_fail_and_pass() -> None:
    fail = check_high_duration(UNBALANCED_FLOAT)
    assert fail.passed is False
    assert fail.offending_ids == ("C",)
    ok = check_high_duration(BALANCED_FLOAT)
    assert ok.passed is True
    assert ok.numerator == 0


def test_check_invalid_dates_not_assessable_fail_and_pass() -> None:
    na = check_invalid_dates(CONNECTED, {}, {}, AS_OF)
    assert na.assessable is False
    assert "not assessable" in na.note

    fail = check_invalid_dates(
        CONNECTED,
        {"A": date(2026, 6, 5)},
        {"B": date(2026, 5, 20)},
        AS_OF,
    )
    assert fail.passed is False
    assert fail.offending_ids == ("A", "B")

    ok = check_invalid_dates(
        CONNECTED,
        {"A": date(2026, 5, 1)},
        {"B": date(2026, 6, 10)},
        AS_OF,
    )
    assert ok.passed is True
    assert ok.numerator == 0


def test_check_resources_fail_and_pass() -> None:
    fail = check_resources(CONNECTED, {"A": ["crew-1"]})
    assert fail.passed is False
    assert fail.offending_ids == ("B", "C")

    ok = check_resources(CONNECTED, {"A": ["crew-1"], "B": ["crew-1"], "C": ["crew-1"]})
    assert ok.passed is True
    assert ok.numerator == 0


def test_check_missed_tasks_not_assessable_fail_and_pass() -> None:
    na = check_missed_tasks(CONNECTED, {}, {}, AS_OF)
    assert na.assessable is False
    assert "not assessable" in na.note

    fail = check_missed_tasks(
        CONNECTED, {"A": date(2026, 5, 1), "B": date(2026, 5, 2)}, {"A": date(2026, 5, 1)}, AS_OF
    )
    assert fail.passed is False
    assert fail.offending_ids == ("B",)

    ok = check_missed_tasks(
        CONNECTED,
        {"A": date(2026, 5, 1), "B": date(2026, 5, 2)},
        {"A": date(2026, 5, 1), "B": date(2026, 5, 2)},
        AS_OF,
    )
    assert ok.passed is True
    assert ok.numerator == 0


def test_check_critical_path_test_not_assessable_fail_and_pass() -> None:
    empty = ScheduleNetwork(activities=(), dependencies=())
    na = check_critical_path_test(empty)
    assert na.assessable is False
    assert "not assessable" in na.note

    ss_first = ScheduleNetwork(
        activities=(Activity("A", 3), Activity("B", 10)),
        dependencies=(Dependency("A", "B", "SS"),),
    )
    fail = check_critical_path_test(ss_first, delay_days=2)
    assert fail.passed is False
    assert fail.offending_ids == ("A",)

    ok = check_critical_path_test(CONNECTED, delay_days=1)
    assert ok.passed is True
    assert ok.numerator == 0


def test_check_cpli_not_assessable_fail_and_pass() -> None:
    empty = ScheduleNetwork(activities=(), dependencies=())
    na = check_cpli(empty, {})
    assert na.assessable is False
    assert "not assessable" in na.note

    fail = check_cpli(CONNECTED, {"A": 0, "B": -10, "C": 0})
    assert fail.passed is False

    ok = check_cpli(CONNECTED, _floats(CONNECTED))
    assert ok.passed is True
    assert ok.ratio == 1.0


def test_check_bei_not_assessable_fail_and_pass() -> None:
    na = check_bei(CONNECTED, {}, {}, AS_OF)
    assert na.assessable is False
    assert "not assessable" in na.note

    fail = check_bei(
        CONNECTED, {"A": date(2026, 5, 1), "B": date(2026, 5, 2)}, {"A": date(2026, 5, 1)}, AS_OF
    )
    assert fail.passed is False
    assert fail.numerator == 1
    assert fail.denominator == 2

    ok = check_bei(
        CONNECTED,
        {"A": date(2026, 5, 1), "B": date(2026, 5, 2)},
        {"A": date(2026, 5, 1), "B": date(2026, 5, 2)},
        AS_OF,
    )
    assert ok.passed is True
    assert ok.ratio == 1.0


def test_assess_full_returns_all_fourteen_checks_in_order() -> None:
    baseline_finish = {"A": date(2026, 5, 1), "B": date(2026, 5, 2), "C": date(2026, 5, 3)}
    actual_finish = {"A": date(2026, 5, 1), "B": date(2026, 5, 2), "C": date(2026, 5, 3)}
    resources = {"A": ["crew-1"], "B": ["crew-1"], "C": ["crew-1"]}
    results = assess_full(
        CONNECTED,
        actual_finish=actual_finish,
        forecast_finish={},
        resources=resources,
        baseline_finish=baseline_finish,
        as_of=AS_OF,
    )
    assert [r.name for r in results] == [
        "logic",
        "leads",
        "lags",
        "relationship_types",
        "hard_constraints",
        "high_float",
        "negative_float",
        "high_duration",
        "invalid_dates",
        "resources",
        "missed_tasks",
        "critical_path_test",
        "cpli",
        "bei",
    ]
    assert all(r.passed for r in results)
