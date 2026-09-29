"""Schedule health checks — 14 pure calculators over
:mod:`driftless.calc.network`. No I/O, no ORM, no wall clock.

The DCMA 14-point assessment is a widely used contracting convention, cited
here only as the source of the thresholds below — never report a result as
"DCMA compliant" or "certified". Check 1 (logic) has no status or
start/finish flag to work with, so the only honest offender is an activity
with neither a predecessor nor a successor. Check 5 (hard constraints)
always reports "not assessable": ``Activity`` has no constraint field to
check. Check 7 (negative float) can never find an offender via this
module's own ``backward_pass``, which always targets the computed project
finish rather than an earlier imposed deadline — it is included per the
DCMA list and only fires if ``floats`` came from elsewhere.

Checks 8-14 need more than ``ScheduleNetwork`` carries (dates, resources,
baseline, status). Rather than widen ``Activity``, they take that data as
explicit extra arguments, including ``as_of`` — never ``date.today()`` — so
a given input set always produces the same result. Where the caller
supplies no judgable data at all (an empty baseline, no dates), a check
returns the same "not assessable" shape check 5 uses rather than inventing
an offender.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from driftless.calc.network import (
    Activity,
    ScheduleNetwork,
    backward_pass,
    critical_path,
    forward_pass,
    total_float,
)

LOGIC_THRESHOLD = 0.05
LEADS_THRESHOLD = 0.0
LAGS_THRESHOLD = 0.05
RELATIONSHIP_TYPE_THRESHOLD = 0.90
HARD_CONSTRAINT_THRESHOLD = 0.0
HIGH_FLOAT_DAYS_THRESHOLD = 44
HIGH_FLOAT_SHARE_THRESHOLD = 0.05
NEGATIVE_FLOAT_THRESHOLD = 0.0
HIGH_DURATION_DAYS_THRESHOLD = 44
HIGH_DURATION_SHARE_THRESHOLD = 0.05
INVALID_DATES_THRESHOLD = 0.0
RESOURCES_THRESHOLD = 0.0
MISSED_TASKS_THRESHOLD = 0.05
CRITICAL_PATH_TEST_THRESHOLD = 0.0
CPLI_THRESHOLD = 0.95
BEI_THRESHOLD = 0.95


@dataclass(frozen=True)
class CheckResult:
    """One check's outcome. ``assessable`` is False only when the network
    model cannot answer at all (check 5); ``note`` then explains why."""

    name: str
    numerator: int
    denominator: int
    ratio: float
    threshold: float
    passed: bool
    offending_ids: tuple[str, ...] = field(default_factory=tuple)
    assessable: bool = True
    note: str = ""


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _result(
    name: str,
    numerator: int,
    denominator: int,
    threshold: float,
    offenders: list[str],
    at_least: bool = False,
) -> CheckResult:
    """``at_least`` flips the pass direction: True for check 4, where more
    of the measured thing (finish-to-start) is better."""
    ratio = _ratio(numerator, denominator)
    passed = ratio >= threshold if at_least else ratio <= threshold
    return CheckResult(
        name, numerator, denominator, ratio, threshold, passed, tuple(sorted(offenders))
    )


def check_logic(network: ScheduleNetwork) -> CheckResult:
    """Share of activities with no predecessor AND no successor."""
    predecessors: dict[str, set[str]] = {a.id: set() for a in network.activities}
    successors: dict[str, set[str]] = {a.id: set() for a in network.activities}
    for dep in network.dependencies:
        predecessors[dep.successor].add(dep.predecessor)
        successors[dep.predecessor].add(dep.successor)
    offenders = [
        a.id
        for a in network.activities
        if len(network.activities) > 1 and not predecessors[a.id] and not successors[a.id]
    ]
    return _result("logic", len(offenders), len(network.activities), LOGIC_THRESHOLD, offenders)


def check_leads(network: ScheduleNetwork) -> CheckResult:
    """Share of dependencies with a negative lag; any at all fails."""
    hits = [dep for dep in network.dependencies if dep.lag < 0]
    offenders = list({d.predecessor for d in hits} | {d.successor for d in hits})
    return _result("leads", len(hits), len(network.dependencies), LEADS_THRESHOLD, offenders)


def check_lags(network: ScheduleNetwork) -> CheckResult:
    """Share of dependencies with a positive lag."""
    hits = [dep for dep in network.dependencies if dep.lag > 0]
    offenders = list({d.predecessor for d in hits} | {d.successor for d in hits})
    return _result("lags", len(hits), len(network.dependencies), LAGS_THRESHOLD, offenders)


def check_relationship_types(network: ScheduleNetwork) -> CheckResult:
    """Share of dependencies that are finish-to-start; passes at or ABOVE
    the threshold, unlike the other checks."""
    hits = [dep for dep in network.dependencies if dep.kind == "FS"]
    non_fs = [dep for dep in network.dependencies if dep.kind != "FS"]
    offenders = list({d.predecessor for d in non_fs} | {d.successor for d in non_fs})
    return _result(
        "relationship_types",
        len(hits),
        len(network.dependencies),
        RELATIONSHIP_TYPE_THRESHOLD,
        offenders,
        at_least=True,
    )


def check_hard_constraints(network: ScheduleNetwork) -> CheckResult:
    """Always "not assessable": ``Activity`` has no constraint field."""
    return CheckResult(
        name="hard_constraints",
        numerator=0,
        denominator=0,
        ratio=0.0,
        threshold=HARD_CONSTRAINT_THRESHOLD,
        passed=True,
        assessable=False,
        note="not assessable: the network carries no constraint field",
    )


def check_high_float(network: ScheduleNetwork, floats: Mapping[str, int]) -> CheckResult:
    """Share of activities whose total float (the caller's own
    ``total_float`` output) exceeds ``HIGH_FLOAT_DAYS_THRESHOLD`` days."""
    offenders = [
        a.id
        for a in network.activities
        if a.id in floats and floats[a.id] > HIGH_FLOAT_DAYS_THRESHOLD
    ]
    return _result(
        "high_float", len(offenders), len(network.activities), HIGH_FLOAT_SHARE_THRESHOLD, offenders
    )


def check_negative_float(network: ScheduleNetwork, floats: Mapping[str, int]) -> CheckResult:
    """Any activity with negative total float (see module docstring)."""
    offenders = [aid for aid, tf in floats.items() if tf < 0]
    return _result(
        "negative_float",
        len(offenders),
        len(network.activities),
        NEGATIVE_FLOAT_THRESHOLD,
        offenders,
    )


def _not_assessable(name: str, threshold: float, note: str) -> CheckResult:
    return CheckResult(
        name=name,
        numerator=0,
        denominator=0,
        ratio=0.0,
        threshold=threshold,
        passed=True,
        assessable=False,
        note=note,
    )


def check_high_duration(network: ScheduleNetwork) -> CheckResult:
    """Share of activities whose own duration exceeds
    ``HIGH_DURATION_DAYS_THRESHOLD`` working days — unlike check 6 (high
    float), this reads ``Activity.duration`` directly, no float mapping."""
    offenders = [a.id for a in network.activities if a.duration > HIGH_DURATION_DAYS_THRESHOLD]
    return _result(
        "high_duration",
        len(offenders),
        len(network.activities),
        HIGH_DURATION_SHARE_THRESHOLD,
        offenders,
    )


def check_invalid_dates(
    network: ScheduleNetwork,
    actual_finish: Mapping[str, date],
    forecast_finish: Mapping[str, date],
    as_of: date,
) -> CheckResult:
    """Share of judged activities with an actual finish after ``as_of`` (a
    date that hasn't happened yet) or a forecast finish before ``as_of`` (a
    forecast still claiming the past). An activity absent from both
    mappings is not judged. "Not assessable" only when neither mapping
    names any activity in ``network`` at all."""
    ids = {a.id for a in network.activities}
    judged = (set(actual_finish) | set(forecast_finish)) & ids
    if not judged:
        return _not_assessable(
            "invalid_dates", INVALID_DATES_THRESHOLD, "not assessable: no dates supplied"
        )
    offenders = [
        aid
        for aid in judged
        if (aid in actual_finish and actual_finish[aid] > as_of)
        or (aid in forecast_finish and forecast_finish[aid] < as_of)
    ]
    return _result("invalid_dates", len(offenders), len(judged), INVALID_DATES_THRESHOLD, offenders)


def check_resources(
    network: ScheduleNetwork, resources: Mapping[str, Sequence[str]]
) -> CheckResult:
    """Share of activities with duration > 0 that carry no assigned
    resource. An activity with zero duration (e.g. a milestone) is never
    judged."""
    candidates = [a for a in network.activities if a.duration > 0]
    offenders = [a.id for a in candidates if not resources.get(a.id)]
    return _result("resources", len(offenders), len(candidates), RESOURCES_THRESHOLD, offenders)


def check_missed_tasks(
    network: ScheduleNetwork,
    baseline_finish: Mapping[str, date],
    actual_finish: Mapping[str, date],
    as_of: date,
) -> CheckResult:
    """Share of activities baselined to finish at or before ``as_of`` that
    have no actual finish recorded. "Not assessable" when no baseline was
    supplied at all."""
    ids = {a.id for a in network.activities}
    due = [aid for aid in baseline_finish if aid in ids and baseline_finish[aid] <= as_of]
    if not baseline_finish:
        return _not_assessable(
            "missed_tasks", MISSED_TASKS_THRESHOLD, "not assessable: no baseline supplied"
        )
    offenders = [aid for aid in due if aid not in actual_finish]
    return _result("missed_tasks", len(offenders), len(due), MISSED_TASKS_THRESHOLD, offenders)


def check_critical_path_test(network: ScheduleNetwork, delay_days: int = 1) -> CheckResult:
    """Delay the critical path's first activity by ``delay_days`` and
    confirm the project finish moves by exactly that many days — the
    network model's own sanity check on itself. "Not assessable" when the
    network has no critical path (e.g. no activities)."""
    early = forward_pass(network)
    late = backward_pass(network, early)
    paths = critical_path(network, early, late)
    if not paths or not paths[0]:
        return _not_assessable(
            "critical_path_test",
            CRITICAL_PATH_TEST_THRESHOLD,
            "not assessable: network has no critical path",
        )
    first_task = paths[0][0]
    original_finish = max(dates.early_finish for dates in early.values())
    activities = tuple(
        Activity(a.id, a.duration + delay_days) if a.id == first_task else a
        for a in network.activities
    )
    delayed = ScheduleNetwork(activities=activities, dependencies=network.dependencies)
    delayed_finish = max(dates.early_finish for dates in forward_pass(delayed).values())
    shift = delayed_finish - original_finish
    passed = shift == delay_days
    return CheckResult(
        name="critical_path_test",
        numerator=0 if passed else 1,
        denominator=1,
        ratio=0.0 if passed else 1.0,
        threshold=CRITICAL_PATH_TEST_THRESHOLD,
        passed=passed,
        offending_ids=() if passed else (first_task,),
    )


def check_cpli(network: ScheduleNetwork, floats: Mapping[str, int]) -> CheckResult:
    """CPLI = (CP length + near-critical float) / CP length: how much
    schedule cushion sits before another path would tie the critical one.
    ``floats`` is the caller's own ``total_float`` output — as with check 7,
    a negative reading (an externally imposed deadline; this module's own
    ``backward_pass`` never produces one) is what drags the ratio below the
    threshold. "Not assessable" when the project has zero length."""
    early = forward_pass(network)
    cp_length = max((dates.early_finish for dates in early.values()), default=0)
    if cp_length == 0:
        return _not_assessable("cpli", CPLI_THRESHOLD, "not assessable: project has zero length")
    non_critical = [f for f in floats.values() if f != 0]
    near_critical_float = min(non_critical) if non_critical else 0
    return _result(
        "cpli", cp_length + near_critical_float, cp_length, CPLI_THRESHOLD, [], at_least=True
    )


def check_bei(
    network: ScheduleNetwork,
    baseline_finish: Mapping[str, date],
    actual_finish: Mapping[str, date],
    as_of: date,
) -> CheckResult:
    """BEI = tasks finished / tasks baselined to finish by ``as_of``. The
    complement view of ``check_missed_tasks``; "not assessable" under the
    same no-baseline condition."""
    ids = {a.id for a in network.activities}
    due = [aid for aid in baseline_finish if aid in ids and baseline_finish[aid] <= as_of]
    if not baseline_finish:
        return _not_assessable("bei", BEI_THRESHOLD, "not assessable: no baseline supplied")
    finished = [aid for aid in due if aid in actual_finish]
    return _result("bei", len(finished), len(due), BEI_THRESHOLD, [], at_least=True)


def assess_full(
    network: ScheduleNetwork,
    *,
    actual_finish: Mapping[str, date],
    forecast_finish: Mapping[str, date],
    resources: Mapping[str, Sequence[str]],
    baseline_finish: Mapping[str, date],
    as_of: date,
    delay_days: int = 1,
) -> tuple[CheckResult, ...]:
    """Checks 1-14, in DCMA order. Checks 8-14 take the extra data
    ``ScheduleNetwork`` cannot carry; see the module docstring."""
    early = forward_pass(network)
    floats = total_float(early, backward_pass(network, early))
    return assess(network) + (
        check_high_duration(network),
        check_invalid_dates(network, actual_finish, forecast_finish, as_of),
        check_resources(network, resources),
        check_missed_tasks(network, baseline_finish, actual_finish, as_of),
        check_critical_path_test(network, delay_days),
        check_cpli(network, floats),
        check_bei(network, baseline_finish, actual_finish, as_of),
    )


def assess(network: ScheduleNetwork) -> tuple[CheckResult, ...]:
    """Checks 1-7, in DCMA order. Computes the forward/backward pass once
    and shares it with the two float-based checks."""
    early = forward_pass(network)
    late = backward_pass(network, early)
    floats = total_float(early, late)
    return (
        check_logic(network),
        check_leads(network),
        check_lags(network),
        check_relationship_types(network),
        check_hard_constraints(network),
        check_high_float(network, floats),
        check_negative_float(network, floats),
    )
