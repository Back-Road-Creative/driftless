"""Estimating techniques — pure functions over plain value objects.

No I/O, no ORM, no clock, in the style of ``calc/evm.py``: every function here
takes numbers and returns an :class:`EstimateScenario`, so a later page or the
basis-of-estimates artifact can show the derivation in the reader's own plain
words rather than re-deriving it.

**Analogous.** Scale a known reference value by the ratio of sizes between the
reference and the target, then apply a judgment adjustment: ``value =
reference_value * (target_size / reference_size) * adjustment``. The whole
estimate is one comparison, so ``low``/``high`` repeat ``value`` — there is no
range to carry without a second reference point.

**Parametric.** Multiply a rate by a quantity: ``value = rate * quantity``.
The multi-driver form (:func:`parametric_multi`) sums that product over
several rate/quantity pairs — one line item per driver, the way a parametric
model usually has more than one cost driver. Both are point estimates, so
``low``/``high`` repeat ``value`` for the same reason as analogous.

**Three-point.** Two distributions over the same three inputs (optimistic,
most likely, pessimistic): triangular weights all three equally, ``mean = (O
+ M + P) / 3``; beta/PERT weights the most likely case four times over,
``mean = (O + 4*M + P) / 6``, with standard deviation ``(P - O) / 6``. PERT's
``low``/``high`` are a confidence range at ``sigma`` standard deviations either
side of the mean (``sigma=1`` by default, the usual ~68% band; pass ``sigma=2``
for the ~95% band) — the range narrows or widens with ``sigma``, it never
changes the mean.

**Bottom-up.** Sum typed component estimates (any :class:`EstimateScenario`,
so a bottom-up estimate can itself be built from analogous, parametric or
three-point leaves): ``value``, ``low`` and ``high`` are each the sum of the
components' own, and the basis lists each component's basis in turn so the
roll-up stays traceable to its parts.

**Refused, not guessed.** Every function refuses a negative input or a
non-positive divisor (a reference size of zero, an optimistic estimate above
the most likely one) with a plain-language ``ValueError`` rather than
producing ``NaN``, ``inf`` or a silently wrong number.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum


class EstimateKind(str, Enum):
    """Every estimating technique this module computes. Totality over this
    enum — one function and one worked example per member — is what the test
    suite walks, so a member added here with no function is a promise unkept."""

    ANALOGOUS = "analogous"
    PARAMETRIC = "parametric"
    THREE_POINT_TRIANGULAR = "three_point_triangular"
    THREE_POINT_BETA = "three_point_beta"
    BOTTOM_UP = "bottom_up"


@dataclass(frozen=True)
class EstimateScenario:
    """One estimate, carrying enough of its own derivation to explain itself.

    ``inputs`` is the technique's own arguments, by name, so a reader (or the
    basis-of-estimates artifact) can show exactly what was fed in without a
    second copy of the call site. ``low``/``high`` bound a single point
    estimate at itself when the technique has no range of its own.
    """

    kind: EstimateKind
    inputs: Mapping[str, float]
    value: float
    low: float
    high: float
    basis: str


def analogous(
    reference_value: float,
    reference_size: float,
    target_size: float,
    adjustment: float = 1.0,
) -> EstimateScenario:
    """Scale ``reference_value`` by the target/reference size ratio, then adjust.

    ``value = reference_value * (target_size / reference_size) * adjustment``.
    Refuses a negative value, a non-positive ``reference_size`` (there is
    nothing to scale against) or a non-positive ``adjustment``.
    """
    if reference_value < 0:
        raise ValueError("reference_value must be >= 0")
    if reference_size <= 0:
        raise ValueError("reference_size must be > 0 — nothing to scale against")
    if target_size < 0:
        raise ValueError("target_size must be >= 0")
    if adjustment <= 0:
        raise ValueError("adjustment must be > 0")

    value = reference_value * (target_size / reference_size) * adjustment
    basis = (
        f"analogous: {reference_value:g} at reference size {reference_size:g}, "
        f"scaled to target size {target_size:g} and adjusted by {adjustment:g}x "
        f"-> {value:g}"
    )
    return EstimateScenario(
        kind=EstimateKind.ANALOGOUS,
        inputs={
            "reference_value": reference_value,
            "reference_size": reference_size,
            "target_size": target_size,
            "adjustment": adjustment,
        },
        value=value,
        low=value,
        high=value,
        basis=basis,
    )


def parametric(rate: float, quantity: float) -> EstimateScenario:
    """Multiply a rate by a quantity: ``value = rate * quantity``.

    Refuses a negative rate or quantity.
    """
    if rate < 0:
        raise ValueError("rate must be >= 0")
    if quantity < 0:
        raise ValueError("quantity must be >= 0")

    value = rate * quantity
    basis = f"parametric: rate {rate:g} x quantity {quantity:g} -> {value:g}"
    return EstimateScenario(
        kind=EstimateKind.PARAMETRIC,
        inputs={"rate": rate, "quantity": quantity},
        value=value,
        low=value,
        high=value,
        basis=basis,
    )


def parametric_multi(drivers: Sequence[tuple[float, float]]) -> EstimateScenario:
    """Sum ``rate * quantity`` over several (rate, quantity) drivers.

    Refuses an empty sequence, or a negative rate or quantity in any driver.
    """
    if not drivers:
        raise ValueError("drivers must be non-empty — nothing to estimate from")
    for rate, quantity in drivers:
        if rate < 0 or quantity < 0:
            raise ValueError("every driver's rate and quantity must be >= 0")

    products = [rate * quantity for rate, quantity in drivers]
    value = sum(products)
    lines = ", ".join(
        f"{rate:g} x {quantity:g} = {product:g}"
        for (rate, quantity), product in zip(drivers, products, strict=True)
    )
    basis = f"parametric (multi-driver): {lines} -> total {value:g}"
    return EstimateScenario(
        kind=EstimateKind.PARAMETRIC,
        inputs={f"driver_{i}": rate * quantity for i, (rate, quantity) in enumerate(drivers)},
        value=value,
        low=value,
        high=value,
        basis=basis,
    )


def _validate_three_point(optimistic: float, most_likely: float, pessimistic: float) -> None:
    if optimistic < 0 or most_likely < 0 or pessimistic < 0:
        raise ValueError("optimistic, most_likely and pessimistic must all be >= 0")
    if optimistic > most_likely:
        raise ValueError("optimistic must be <= most_likely")
    if most_likely > pessimistic:
        raise ValueError("most_likely must be <= pessimistic")


def three_point_triangular(
    optimistic: float, most_likely: float, pessimistic: float
) -> EstimateScenario:
    """Triangular three-point estimate, weighting all three points equally.

    ``mean = (O + M + P) / 3``. ``low``/``high`` are the optimistic and
    pessimistic points themselves — the estimate's own stated range. Refuses
    a negative input or a point out of order (``optimistic <= most_likely <=
    pessimistic``).
    """
    _validate_three_point(optimistic, most_likely, pessimistic)
    value = (optimistic + most_likely + pessimistic) / 3
    basis = (
        f"three-point (triangular): (O={optimistic:g} + M={most_likely:g} + "
        f"P={pessimistic:g}) / 3 -> {value:g}"
    )
    return EstimateScenario(
        kind=EstimateKind.THREE_POINT_TRIANGULAR,
        inputs={
            "optimistic": optimistic,
            "most_likely": most_likely,
            "pessimistic": pessimistic,
        },
        value=value,
        low=optimistic,
        high=pessimistic,
        basis=basis,
    )


def three_point_beta(
    optimistic: float, most_likely: float, pessimistic: float, sigma: float = 1.0
) -> EstimateScenario:
    """Beta/PERT three-point estimate, weighting the most likely point x4.

    ``mean = (O + 4*M + P) / 6``, standard deviation ``(P - O) / 6``.
    ``low``/``high`` are the mean +/- ``sigma`` standard deviations — ``sigma=1``
    for the ~68% band, ``sigma=2`` for the ~95% band. Refuses a negative
    input, a point out of order, or a non-positive ``sigma``.
    """
    _validate_three_point(optimistic, most_likely, pessimistic)
    if sigma <= 0:
        raise ValueError("sigma must be > 0")

    value = (optimistic + 4 * most_likely + pessimistic) / 6
    std_dev = (pessimistic - optimistic) / 6
    low = value - sigma * std_dev
    high = value + sigma * std_dev
    basis = (
        f"three-point (beta/PERT): (O={optimistic:g} + 4*M={most_likely:g} + "
        f"P={pessimistic:g}) / 6 -> {value:g}, std dev {std_dev:g}, "
        f"+/-{sigma:g} sigma range [{low:g}, {high:g}]"
    )
    return EstimateScenario(
        kind=EstimateKind.THREE_POINT_BETA,
        inputs={
            "optimistic": optimistic,
            "most_likely": most_likely,
            "pessimistic": pessimistic,
            "sigma": sigma,
        },
        value=value,
        low=low,
        high=high,
        basis=basis,
    )


def bottom_up(components: Sequence[EstimateScenario]) -> EstimateScenario:
    """Sum typed component estimates into one roll-up.

    ``value``, ``low`` and ``high`` are each the sum of the components' own;
    the basis lists each component's basis in turn, so the roll-up stays
    traceable to its parts. Refuses an empty sequence.
    """
    if not components:
        raise ValueError("components must be non-empty — nothing to roll up")

    value = sum(component.value for component in components)
    low = sum(component.low for component in components)
    high = sum(component.high for component in components)
    lines = "; ".join(component.basis for component in components)
    basis = f"bottom-up: sum of {len(components)} components -> {value:g} ({lines})"
    return EstimateScenario(
        kind=EstimateKind.BOTTOM_UP,
        inputs={f"component_{i}": component.value for i, component in enumerate(components)},
        value=value,
        low=low,
        high=high,
        basis=basis,
    )
