"""Tests for the estimating calculator core.

Every :class:`~driftless.calc.estimating.EstimateKind` gets a worked example
matching a hand computation, walked by totality rather than sampled, plus
parametrized edge cases (zero size, optimistic-above-most-likely, negative
inputs) and a determinism check.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from driftless.calc.estimating import (
    EstimateKind,
    EstimateScenario,
    analogous,
    bottom_up,
    parametric,
    parametric_multi,
    three_point_beta,
    three_point_triangular,
)

# One worked example per EstimateKind, hand-computed:
WORKED_EXAMPLES: dict[EstimateKind, tuple[Callable[[], EstimateScenario], float]] = {
    # Reference: 100 at size 10; target size 25; adjustment 1.2.
    # value = 100 * (25 / 10) * 1.2 = 300.
    EstimateKind.ANALOGOUS: (
        lambda: analogous(
            reference_value=100.0, reference_size=10.0, target_size=25.0, adjustment=1.2
        ),
        300.0,
    ),
    # rate 50, quantity 8 -> 400.
    EstimateKind.PARAMETRIC: (
        lambda: parametric(rate=50.0, quantity=8.0),
        400.0,
    ),
    # O=3, M=6, P=15 -> (3 + 6 + 15) / 3 = 8.
    EstimateKind.THREE_POINT_TRIANGULAR: (
        lambda: three_point_triangular(optimistic=3.0, most_likely=6.0, pessimistic=15.0),
        8.0,
    ),
    # O=3, M=6, P=15 -> (3 + 24 + 15) / 6 = 7.
    EstimateKind.THREE_POINT_BETA: (
        lambda: three_point_beta(optimistic=3.0, most_likely=6.0, pessimistic=15.0),
        7.0,
    ),
    # Two components worth 100 and 250 -> 350.
    EstimateKind.BOTTOM_UP: (
        lambda: bottom_up(
            [
                analogous(reference_value=100.0, reference_size=10.0, target_size=10.0),
                parametric(rate=50.0, quantity=5.0),
            ]
        ),
        350.0,
    ),
}


def test_every_estimate_kind_has_a_function_and_a_worked_example() -> None:
    assert set(WORKED_EXAMPLES) == set(EstimateKind)


@pytest.mark.parametrize("kind", list(EstimateKind))
def test_worked_example_matches_hand_computation(kind: EstimateKind) -> None:
    build, expected = WORKED_EXAMPLES[kind]
    scenario = build()
    assert isinstance(scenario, EstimateScenario)
    assert scenario.kind == kind
    assert scenario.value == pytest.approx(expected)
    assert scenario.basis


def test_three_point_triangular_range_is_its_own_endpoints() -> None:
    scenario = three_point_triangular(optimistic=3.0, most_likely=6.0, pessimistic=15.0)
    assert scenario.low == 3.0
    assert scenario.high == 15.0


def test_three_point_beta_confidence_range_widens_with_sigma() -> None:
    # std dev = (15 - 3) / 6 = 2. Mean = 7.
    one_sigma = three_point_beta(optimistic=3.0, most_likely=6.0, pessimistic=15.0, sigma=1.0)
    two_sigma = three_point_beta(optimistic=3.0, most_likely=6.0, pessimistic=15.0, sigma=2.0)
    assert one_sigma.low == pytest.approx(5.0)
    assert one_sigma.high == pytest.approx(9.0)
    assert two_sigma.low == pytest.approx(3.0)
    assert two_sigma.high == pytest.approx(11.0)
    assert two_sigma.low < one_sigma.low
    assert two_sigma.high > one_sigma.high


def test_parametric_multi_sums_each_driver() -> None:
    scenario = parametric_multi([(50.0, 8.0), (10.0, 3.0)])
    assert scenario.kind == EstimateKind.PARAMETRIC
    assert scenario.value == pytest.approx(430.0)  # 400 + 30


def test_bottom_up_basis_traces_each_component() -> None:
    a = analogous(reference_value=100.0, reference_size=10.0, target_size=10.0)
    b = parametric(rate=50.0, quantity=5.0)
    scenario = bottom_up([a, b])
    assert a.basis in scenario.basis
    assert b.basis in scenario.basis


def test_scenarios_are_deterministic_for_the_same_inputs() -> None:
    assert analogous(100.0, 10.0, 25.0, 1.2) == analogous(100.0, 10.0, 25.0, 1.2)
    assert three_point_beta(3.0, 6.0, 15.0) == three_point_beta(3.0, 6.0, 15.0)


def test_analogous_zero_target_size_is_a_zero_estimate() -> None:
    scenario = analogous(reference_value=100.0, reference_size=10.0, target_size=0.0)
    assert scenario.value == 0.0


def test_analogous_zero_reference_size_is_refused() -> None:
    with pytest.raises(ValueError, match="reference_size"):
        analogous(reference_value=100.0, reference_size=0.0, target_size=25.0)


@pytest.mark.parametrize(
    "call",
    [
        lambda: analogous(reference_value=-1.0, reference_size=10.0, target_size=25.0),
        lambda: analogous(reference_value=100.0, reference_size=-10.0, target_size=25.0),
        lambda: analogous(reference_value=100.0, reference_size=10.0, target_size=-1.0),
        lambda: parametric(rate=-1.0, quantity=8.0),
        lambda: parametric(rate=50.0, quantity=-1.0),
        lambda: three_point_triangular(optimistic=-1.0, most_likely=6.0, pessimistic=15.0),
        lambda: three_point_beta(optimistic=3.0, most_likely=-6.0, pessimistic=15.0),
    ],
)
def test_negative_inputs_are_refused_with_a_plain_message(call: object) -> None:
    with pytest.raises(ValueError):
        call()  # type: ignore[operator]


def test_three_point_optimistic_above_most_likely_is_refused() -> None:
    with pytest.raises(ValueError, match="optimistic must be <= most_likely"):
        three_point_triangular(optimistic=10.0, most_likely=6.0, pessimistic=15.0)
    with pytest.raises(ValueError, match="optimistic must be <= most_likely"):
        three_point_beta(optimistic=10.0, most_likely=6.0, pessimistic=15.0)


def test_bottom_up_refuses_an_empty_sequence() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        bottom_up([])


def test_parametric_multi_refuses_an_empty_sequence() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        parametric_multi([])
