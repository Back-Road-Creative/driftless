"""Risk analysis: qualitative scoring, quantitative simulation, and decision support.

Pure functions over frozen value objects: no I/O, no ORM, no wall clock. Callers adapt a
stored ``Risk`` row (``driftless/models/records.py:Risk``) into plain probability/impact
numbers rather than handing the ORM row in — the same convention ``calc.evm`` and
``calc.forecast`` already use. The register type is ``driftless.calc.forecast.Risk``,
reused rather than duplicated: it already carries probability, impact and the derived
``exposure`` this module's simulation sums.

This is RISK analysis. ``driftless.calc.forecast.monte_carlo_completion`` simulates
SCHEDULE completion from sprint velocity and is untouched here — a different question
answered by a different function, not a case this module's simulation subsumes.

**Qualitative** (Perform Qualitative Risk Analysis): a probability scale and an impact
scale, each a ``RiskScale`` of named ``Level``s, feed a plain probability x impact
``score`` looked up in a ``matrix`` — a dict from (probability level name, impact level
name) to a number, banded low/moderate/high by ``band_for``. ``DEFAULT_MATRIX`` is the
usual 5x5 (product of 1..5 level index), and every one of its 25 cells resolves to a band
(checked in the test suite, not asserted here — a matrix a caller supplies is validated
the same way, by ``score`` raising rather than a silent gap in the bands). Reserved for
later PERT-style calibration (`ThreePointEstimate`) rather than a scale on its own, since a
project ranks risks with the scale before it ever estimates one in three points.

**Quantitative** (Perform Quantitative Risk Analysis): ``simulate_exposure`` treats each
risk in a register as an independent Bernoulli trial — it occurs, contributing its full
impact, with its own probability, or it does not — and sums an iteration's occurrences
into that iteration's total exposure. Seeded, so the same seed and register give
byte-identical output; the RNG is drawn in register order, so appending a risk to a
register only ever adds a non-negative amount to every iteration's total, which is what
keeps p90 from falling when the register grows (checked in the test suite).
``expected_monetary_value`` and ``decision_tree`` are the textbook EMV techniques;
``sensitivity`` orders a set of factors into a tornado — the largest swing from the base
case first; ``influence_diagram`` hands the same relationships back as a nodes/edges
shape a later report page can draw, validated for unknown node kinds and dangling edges.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from driftless.calc.forecast import Risk

_LEVEL_NAMES: tuple[str, ...] = ("very_low", "low", "moderate", "high", "very_high")


@dataclass(frozen=True)
class Level:
    """One named band of a scale, inclusive at both ends."""

    name: str
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if self.upper < self.lower:
            raise ValueError(f"level {self.name}: upper below lower")


@dataclass(frozen=True)
class RiskScale:
    """An ordered set of ``Level``s covering a probability or impact axis."""

    levels: tuple[Level, ...]

    def __post_init__(self) -> None:
        if not self.levels:
            raise ValueError("a risk scale needs at least one level")

    def level_for(self, value: float) -> Level:
        """The first level whose bounds contain ``value``.

        Raises ``ValueError`` when no level covers it — a caller outside the scale's own
        range gets a refusal, never a nearest-band guess.
        """
        for level in self.levels:
            if level.lower <= value <= level.upper:
                return level
        raise ValueError(f"{value} falls outside every level of this scale")


DEFAULT_PROBABILITY_SCALE = RiskScale(
    tuple(Level(name, i / 5, (i + 1) / 5) for i, name in enumerate(_LEVEL_NAMES))
)
DEFAULT_IMPACT_SCALE = RiskScale(
    tuple(Level(name, i / 5, (i + 1) / 5) for i, name in enumerate(_LEVEL_NAMES))
)

# 5x5 product matrix: 1..5 for each axis in scale order, the usual textbook P x I grid.
DEFAULT_MATRIX: dict[tuple[str, str], int] = {
    (p_name, i_name): (p_index + 1) * (i_index + 1)
    for p_index, p_name in enumerate(_LEVEL_NAMES)
    for i_index, i_name in enumerate(_LEVEL_NAMES)
}

# Every product 1..25 must resolve; the thresholds are chosen to cover that whole range.
_BAND_THRESHOLDS: tuple[tuple[int, str], ...] = ((4, "low"), (12, "moderate"), (25, "high"))


def band_for(value: int) -> str:
    """The plain-words band (low/moderate/high) a matrix score falls into."""
    for threshold, band in _BAND_THRESHOLDS:
        if value <= threshold:
            return band
    raise ValueError(f"score {value} exceeds the matrix's highest band")


def score(
    probability_level: str,
    impact_level: str,
    matrix: Mapping[tuple[str, str], int] | None = None,
) -> tuple[int, str]:
    """Look up a probability level x impact level pair in ``matrix`` (``DEFAULT_MATRIX`` if
    none given), returning its numeric score and plain-words band."""
    active = matrix if matrix is not None else DEFAULT_MATRIX
    key = (probability_level, impact_level)
    if key not in active:
        raise ValueError(
            f"no matrix entry for probability={probability_level!r}, impact={impact_level!r}"
        )
    value = active[key]
    return value, band_for(value)


_RBS_SUMMARIES: dict[str, str] = {
    "technical": "Risk from the solution itself: design, performance, quality, technology.",
    "external": "Risk from outside the project's control: regulatory, market, weather, suppliers.",
    "organizational": "Risk from the performing organisation: funding, priorities, resourcing.",
    "project_management": "Risk from how the project is run: estimating, planning, controlling.",
}


class RiskBreakdownStructureCategory(Enum):
    """The standard RBS groupings a risk is classified into, each with a plain summary."""

    TECHNICAL = "technical"
    EXTERNAL = "external"
    ORGANIZATIONAL = "organizational"
    PROJECT_MANAGEMENT = "project_management"

    @property
    def summary(self) -> str:
        return _RBS_SUMMARIES[self.value]


@dataclass(frozen=True)
class ThreePointEstimate:
    """Optimistic/most-likely/pessimistic inputs to the PERT and triangular means.

    Implemented locally rather than imported: ``driftless.calc.estimating`` does not exist
    yet on this base. If a general three-point estimator lands there later, this class
    should be replaced with that one rather than kept as a second copy of the same maths.
    """

    optimistic: float
    most_likely: float
    pessimistic: float

    def __post_init__(self) -> None:
        if not self.optimistic <= self.most_likely <= self.pessimistic:
            raise ValueError("need optimistic <= most_likely <= pessimistic")

    @property
    def pert_mean(self) -> float:
        """The PERT (beta) weighted mean: (O + 4M + P) / 6."""
        return (self.optimistic + 4 * self.most_likely + self.pessimistic) / 6

    @property
    def pert_std_dev(self) -> float:
        """The PERT standard deviation: (P - O) / 6."""
        return (self.pessimistic - self.optimistic) / 6

    @property
    def triangular_mean(self) -> float:
        """The plain triangular-distribution mean: (O + M + P) / 3."""
        return (self.optimistic + self.most_likely + self.pessimistic) / 3


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    """The value at ``fraction`` through ``sorted_values``, ascending."""
    index = min(len(sorted_values) - 1, math.ceil(fraction * len(sorted_values)) - 1)
    index = max(0, index)
    return sorted_values[index]


@dataclass(frozen=True)
class RiskSimulation:
    """p50/p80/p90 and mean total exposure from a seeded Monte Carlo run."""

    iterations: int
    seed: int
    mean: float
    p50: float
    p80: float
    p90: float


def simulate_exposure(risks: Sequence[Risk], iterations: int, seed: int) -> RiskSimulation:
    """Simulate total exposure across ``risks`` as independent Bernoulli trials.

    Each of ``iterations`` trials draws, in register order, whether each risk occurs
    (probability ``risk.probability``) and sums the impacts of the ones that do. Fully
    seeded — the same ``seed`` and register give byte-identical output. Raises
    ``ValueError`` when ``iterations`` is not positive; a risk with a probability outside
    0..1 is refused by ``Risk`` itself, at construction, never here.
    """
    if iterations <= 0:
        raise ValueError("iterations must be > 0")

    rng = random.Random(seed)
    totals: list[float] = []
    for _ in range(iterations):
        total = 0.0
        for risk in risks:
            if rng.random() < risk.probability:
                total += risk.impact
        totals.append(total)
    totals.sort()

    mean = sum(totals) / len(totals)
    return RiskSimulation(
        iterations=iterations,
        seed=seed,
        mean=mean,
        p50=_percentile(totals, 0.5),
        p80=_percentile(totals, 0.8),
        p90=_percentile(totals, 0.9),
    )


@dataclass(frozen=True)
class Outcome:
    """One branch's chance of a value: how often, and what it is worth when it happens."""

    probability: float
    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("outcome probability must be between 0.0 and 1.0")


def expected_monetary_value(outcomes: Sequence[Outcome]) -> float:
    """EMV = sum(probability x value) across ``outcomes``.

    Raises ``ValueError`` when ``outcomes`` is empty or its probabilities do not sum to 1 —
    an EMV over a partial or over-complete outcome set is not a real expectation.
    """
    if not outcomes:
        raise ValueError("expected_monetary_value needs at least one outcome")
    total_probability = sum(outcome.probability for outcome in outcomes)
    if not math.isclose(total_probability, 1.0, abs_tol=1e-9):
        raise ValueError(f"outcome probabilities must sum to 1.0, got {total_probability}")
    return sum(outcome.probability * outcome.value for outcome in outcomes)


@dataclass(frozen=True)
class DecisionBranch:
    """One choice in a decision tree: a name and the outcomes that follow it."""

    name: str
    outcomes: tuple[Outcome, ...]

    @property
    def emv(self) -> float:
        return expected_monetary_value(self.outcomes)


@dataclass(frozen=True)
class DecisionTreeResult:
    """Every branch considered, and the one with the highest EMV."""

    branches: tuple[DecisionBranch, ...]
    best: DecisionBranch


def decision_tree(branches: Sequence[DecisionBranch]) -> DecisionTreeResult:
    """Compute every branch's EMV and name the best one.

    A tie keeps the first branch in ``branches`` with the highest EMV — the input order is
    the tie-break, since nothing here has grounds to prefer one equally-good branch over
    another. Raises ``ValueError`` on an empty set of branches.
    """
    if not branches:
        raise ValueError("decision_tree needs at least one branch")
    best = max(branches, key=lambda branch: branch.emv)
    return DecisionTreeResult(branches=tuple(branches), best=best)


@dataclass(frozen=True)
class SensitivityFactor:
    """One factor's low/high project outcome, holding every other factor at the base case."""

    name: str
    low: float
    high: float

    @property
    def swing(self) -> float:
        """How far this factor alone can move the outcome, in either direction."""
        return abs(self.high - self.low)


@dataclass(frozen=True)
class TornadoRow:
    """One factor's place in tornado order."""

    name: str
    low: float
    high: float
    swing: float


def sensitivity(base: float, factors: Sequence[SensitivityFactor]) -> tuple[TornadoRow, ...]:
    """Order ``factors`` into a tornado: the largest swing first.

    ``base`` documents the case every factor's low/high already varies from; it does not
    change the ordering, which depends only on each factor's own swing. Raises
    ``ValueError`` on an empty set of factors.
    """
    if not factors:
        raise ValueError("sensitivity needs at least one factor")
    del base  # documented above; the ordering never depends on it
    rows = [TornadoRow(f.name, f.low, f.high, f.swing) for f in factors]
    return tuple(sorted(rows, key=lambda row: (-row.swing, row.name)))


_INFLUENCE_KINDS = frozenset({"decision", "chance", "value"})


@dataclass(frozen=True)
class InfluenceNode:
    """One node of an influence diagram: a decision, a chance event, or a value."""

    id: str
    kind: str
    label: str


@dataclass(frozen=True)
class InfluenceEdge:
    """One directed influence from ``source`` to ``target``, both node ids."""

    source: str
    target: str


@dataclass(frozen=True)
class InfluenceDiagram:
    """An assembled, validated influence diagram — a shape a later report page can draw."""

    nodes: tuple[InfluenceNode, ...]
    edges: tuple[InfluenceEdge, ...]


def influence_diagram(
    nodes: Sequence[InfluenceNode], edges: Sequence[InfluenceEdge]
) -> InfluenceDiagram:
    """Assemble ``nodes`` and ``edges`` into one immutable diagram.

    Raises ``ValueError`` on a node whose ``kind`` is not one of decision/chance/value, or
    on an edge naming a node id neither end of it defines.
    """
    bad_kinds = [node.id for node in nodes if node.kind not in _INFLUENCE_KINDS]
    if bad_kinds:
        raise ValueError(f"unknown node kind for: {bad_kinds}")
    ids = {node.id for node in nodes}
    dangling = [edge for edge in edges if edge.source not in ids or edge.target not in ids]
    if dangling:
        raise ValueError(f"edge references an unknown node: {dangling}")
    return InfluenceDiagram(nodes=tuple(nodes), edges=tuple(edges))
