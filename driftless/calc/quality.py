"""Quality tools — pure functions over plain values and frozen dataclasses.

No I/O, no ORM, no wall clock: every function here takes only the numbers or
mappings the caller already has in hand and returns a plain answer, the same
way ``driftless.calc.evm`` does. Nothing here imports ``driftless.models``,
``driftless.db`` or another ``driftless.calc`` module — a caller adapting
``QualityMeasurement`` rows into ``control_chart`` inputs, for instance, does
that adaptation itself.

Six tools live here: a control chart (mean, ±3σ limits, out-of-control points
and the rule-of-seven run signal), a Pareto split (cumulative share and the
80% "vital few" cut), a statistical sampling plan (sample size from a stated
formula), cost of quality (conformance vs non-conformance, with a plain-words
read), an Ishikawa/fishbone shape plus a five-whys chain helper, and a
checklist pass/fail that names its failing items.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

#: z-scores for the confidence levels ``sampling_plan`` accepts. Any other
#: value is refused rather than interpolated silently.
CONFIDENCE_Z: dict[float, float] = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}


@dataclass(frozen=True)
class ControlChartResult:
    """One control chart's summary: center line, ±3σ limits, and the two
    signals that matter — a point outside the limits, and a run of seven
    consecutive points on the same side of the mean."""

    mean: float
    sigma: float
    ucl: float
    lcl: float
    out_of_control: tuple[int, ...]
    out_of_spec: tuple[int, ...]
    run_signal: str | None


def control_chart(
    measurements: Sequence[float],
    spec_lower: float | None = None,
    spec_upper: float | None = None,
) -> ControlChartResult:
    """Mean, sample ±3σ control limits, and both quality signals.

    ``out_of_control`` names points beyond the statistical ±3σ limits
    computed from ``measurements`` itself; ``out_of_spec`` separately names
    points outside the caller's own tolerance (``spec_lower``/``spec_upper``,
    either or both optional) — a point can be in statistical control and
    still fail its spec, or the reverse. Needs at least 2 measurements to
    estimate a spread; fewer raises rather than dividing by zero.
    """
    if len(measurements) < 2:
        raise ValueError("control_chart needs at least 2 measurements to estimate a limit")
    mean = sum(measurements) / len(measurements)
    variance = sum((x - mean) ** 2 for x in measurements) / (len(measurements) - 1)
    sigma = math.sqrt(variance)
    ucl = mean + 3 * sigma
    lcl = mean - 3 * sigma
    out_of_control = tuple(i for i, x in enumerate(measurements) if x > ucl or x < lcl)
    out_of_spec = tuple(
        i
        for i, x in enumerate(measurements)
        if (spec_lower is not None and x < spec_lower)
        or (spec_upper is not None and x > spec_upper)
    )
    return ControlChartResult(
        mean=mean,
        sigma=sigma,
        ucl=ucl,
        lcl=lcl,
        out_of_control=out_of_control,
        out_of_spec=out_of_spec,
        run_signal=_rule_of_seven(measurements, mean),
    )


def _rule_of_seven(measurements: Sequence[float], mean: float) -> str | None:
    """Seven consecutive points on the same side of the mean is a nonrandom
    pattern — a likely process shift — even when every point sits inside the
    ±3σ limits. A point exactly on the mean breaks any run."""
    run_start = 0
    side = 0
    for i, x in enumerate(measurements):
        current_side = 1 if x > mean else (-1 if x < mean else 0)
        if current_side == 0 or current_side != side:
            side = current_side
            run_start = i
        if side != 0 and i - run_start + 1 >= 7:
            direction = "above" if side == 1 else "below"
            return (
                f"points {run_start + 1}-{i + 1} are all {direction} the mean, a rule-of-seven "
                "run signaling a likely process shift"
            )
    return None


@dataclass(frozen=True)
class ParetoEntry:
    """One category's count, its share of the total, and the running total
    up to and including it — the cumulative-share line a Pareto chart draws."""

    category: str
    count: int
    share: float
    cumulative_share: float


@dataclass(frozen=True)
class ParetoResult:
    """Categories ranked largest-count-first, plus the "vital few" that
    together reach 80% of the total."""

    entries: tuple[ParetoEntry, ...]
    vital_few: tuple[str, ...]


def pareto(counts: Mapping[str, int]) -> ParetoResult:
    """Rank ``counts`` largest-first and cut the "vital few" at 80% cumulative
    share. An empty or all-zero ``counts`` answers an empty result rather than
    dividing by zero — there is nothing to rank."""
    total = sum(counts.values())
    if total <= 0:
        return ParetoResult(entries=(), vital_few=())
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    entries: list[ParetoEntry] = []
    vital_few: list[str] = []
    cumulative = 0
    crossed = False
    for category, count in ordered:
        cumulative += count
        cumulative_share = cumulative / total
        entries.append(
            ParetoEntry(
                category=category,
                count=count,
                share=count / total,
                cumulative_share=cumulative_share,
            )
        )
        if not crossed:
            vital_few.append(category)
        if cumulative_share >= 0.8:
            crossed = True
    return ParetoResult(entries=tuple(entries), vital_few=tuple(vital_few))


@dataclass(frozen=True)
class SamplingPlanResult:
    """The sample size a plan needs, plus the formula it came from —
    written out so the number can be checked by hand, not just trusted."""

    sample_size: int
    formula: str


def sampling_plan(population: int, confidence: float, margin: float) -> SamplingPlanResult:
    """Sample size for estimating a proportion from a finite population.

    ``n0 = z^2 x p(1-p) / e^2`` with the worst-case ``p = 0.5`` (the value
    that maximizes the required sample, so the plan never undersizes), then
    finite-population-corrected: ``n = n0 / (1 + (n0 - 1) / N)``, rounded up
    and capped at the population itself. ``confidence`` must be one of the
    z-scores in ``CONFIDENCE_Z``; interpolating an arbitrary confidence level
    invites a silently wrong z-score, so it is refused instead.
    """
    if population < 1:
        raise ValueError("sampling_plan needs a population of at least 1")
    if confidence not in CONFIDENCE_Z:
        raise ValueError(f"confidence must be one of {sorted(CONFIDENCE_Z)}, got {confidence}")
    if not 0 < margin < 1:
        raise ValueError("margin must be between 0 and 1")
    z = CONFIDENCE_Z[confidence]
    n0 = (z**2 * 0.25) / (margin**2)
    n = n0 / (1 + (n0 - 1) / population)
    sample_size = min(population, math.ceil(n))
    formula = (
        f"n0 = z^2 x 0.25 / e^2 with z={z} (confidence {confidence:.0%}) and e={margin} margin "
        "of error, worst-case p=0.5; finite-population-corrected n = n0 / (1 + (n0 - 1) / N), "
        "rounded up and capped at the population"
    )
    return SamplingPlanResult(sample_size=sample_size, formula=formula)


@dataclass(frozen=True)
class CostOfQualityResult:
    """Conformance spend (prevention + appraisal) against non-conformance
    spend (internal + external failure), with a plain-words read of which
    side is winning."""

    conformance: float
    nonconformance: float
    total: float
    conformance_share: float | None
    interpretation: str


def cost_of_quality(
    prevention: float, appraisal: float, internal_failure: float, external_failure: float
) -> CostOfQualityResult:
    """Split cost-of-quality spend into conformance vs non-conformance and
    say in plain words which is larger. Negative inputs are refused — a cost
    category cannot be a credit here."""
    for name, value in (
        ("prevention", prevention),
        ("appraisal", appraisal),
        ("internal_failure", internal_failure),
        ("external_failure", external_failure),
    ):
        if value < 0:
            raise ValueError(f"{name} cost cannot be negative")
    conformance = prevention + appraisal
    nonconformance = internal_failure + external_failure
    total = conformance + nonconformance
    if total == 0:
        return CostOfQualityResult(
            conformance=0.0,
            nonconformance=0.0,
            total=0.0,
            conformance_share=None,
            interpretation="No quality cost recorded — nothing spent on prevention, appraisal, "
            "or failure.",
        )
    if nonconformance > conformance:
        interpretation = (
            "Failure costs exceed prevention and appraisal spend — quality is being paid for "
            "after the fact, not built in."
        )
    elif nonconformance < conformance:
        interpretation = (
            "Prevention and appraisal spend exceeds failure costs — quality investment is "
            "front-loaded, the cheaper place to pay for it."
        )
    else:
        interpretation = "Conformance and non-conformance costs are exactly balanced."
    return CostOfQualityResult(
        conformance=conformance,
        nonconformance=nonconformance,
        total=total,
        conformance_share=conformance / total,
        interpretation=interpretation,
    )


@dataclass(frozen=True)
class FishboneCause:
    """One Ishikawa category (method, machine, material, people, measurement,
    environment, ...) and the candidate causes filed under it."""

    category: str
    causes: tuple[str, ...]


@dataclass(frozen=True)
class FishboneDiagram:
    """The effect under investigation, plus its causes sorted by category —
    the fishbone shape itself."""

    effect: str
    categories: tuple[FishboneCause, ...]


def root_cause(effect: str, causes: Mapping[str, Sequence[str]]) -> FishboneDiagram:
    """Build a fishbone diagram: ``effect`` is the observed problem, ``causes``
    maps each category name to the candidate causes filed under it."""
    return FishboneDiagram(
        effect=effect,
        categories=tuple(
            FishboneCause(category=category, causes=tuple(items))
            for category, items in causes.items()
        ),
    )


@dataclass(frozen=True)
class FiveWhys:
    """One five-whys chain: each answer in order, and the last one — the
    candidate root cause the chain bottomed out at."""

    chain: tuple[str, ...]
    root_cause: str


def five_whys(chain: Sequence[str]) -> FiveWhys:
    """Wrap a why-chain and name its last answer as the candidate root cause.
    An empty chain has no root cause to name, so it is refused."""
    if not chain:
        raise ValueError("five_whys needs at least one answer in the chain")
    frozen_chain = tuple(chain)
    return FiveWhys(chain=frozen_chain, root_cause=frozen_chain[-1])


@dataclass(frozen=True)
class ChecklistResult:
    """Whether every item passed, and which ones did not — named, not just
    counted, so the failing items can be acted on directly."""

    passed: bool
    failing: tuple[str, ...]


def checklist_result(items: Mapping[str, bool]) -> ChecklistResult:
    """Pass/fail a checklist and name the items that failed. An empty
    checklist passes vacuously — there is nothing to fail."""
    failing = tuple(name for name, ok in items.items() if not ok)
    return ChecklistResult(passed=not failing, failing=failing)
