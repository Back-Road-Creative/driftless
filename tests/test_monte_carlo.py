"""The Monte Carlo completion forecast: seeded, so it is reproducible.

The property that matters is determinism — the same seed gives byte-identical
percentiles — because a report that regenerates differently each run is worse
than none. That is pinned to literal dates, not to a run-twice comparison. The
edges (empty history, zero remaining, a zero-velocity team) are pinned too.
"""

from datetime import date

import pytest

from driftless.calc import forecast as fc

AS_OF = date(2026, 3, 31)


def _history(*points: float) -> list[fc.Sprint]:
    return [
        fc.Sprint(name=f"s{i}", ended_on=date(2026, 1, i + 1), completed_points=p)
        for i, p in enumerate(points)
    ]


def test_a_pinned_seed_yields_these_literal_dates() -> None:
    """Seed 42 over this history gives exactly these percentiles, forever.

    A run-twice self-comparison only proves the function agrees with itself
    within one process; literal dates pin the sampled distribution itself, so
    any drift in the engine fails this test loudly.
    """
    history = _history(5.0, 12.0, 20.0, 35.0)
    result = fc.monte_carlo_completion(history, 100.0, AS_OF, seed=42, trials=200)
    assert (result.sprints_p50, result.sprints_p80, result.sprints_p90) == (6, 7, 8)
    assert (result.p50, result.p80, result.p90) == (
        date(2026, 6, 23),
        date(2026, 7, 7),
        date(2026, 7, 21),
    )


def test_percentiles_are_ordered_and_after_as_of() -> None:
    history = _history(20.0, 25.0, 18.0, 30.0)
    result = fc.monte_carlo_completion(history, 100.0, AS_OF, seed=7, trials=500)
    assert result.p50 is not None and result.p90 is not None
    assert AS_OF < result.p50 <= result.p90  # later percentiles are no earlier
    assert result.sprints_p50 is not None and result.sprints_p50 >= 4  # 100 / ~23 per sprint


def test_zero_remaining_completes_at_as_of() -> None:
    result = fc.monte_carlo_completion(_history(20.0), 0.0, AS_OF, seed=1)
    assert (result.p50, result.p80, result.p90) == (AS_OF, AS_OF, AS_OF)


def test_a_stalled_team_never_completes() -> None:
    result = fc.monte_carlo_completion(_history(0.0, 0.0), 50.0, AS_OF, seed=1, trials=50)
    assert result.p50 is None and result.p90 is None


def test_empty_history_and_bad_inputs_are_refused() -> None:
    with pytest.raises(ValueError):
        fc.monte_carlo_completion([], 10.0, AS_OF, seed=1)
    with pytest.raises(ValueError):
        fc.monte_carlo_completion(_history(10.0), -1.0, AS_OF, seed=1)
    with pytest.raises(ValueError):
        fc.monte_carlo_completion(_history(10.0), 10.0, AS_OF, seed=1, trials=0)
