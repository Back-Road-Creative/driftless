"""Procurement decisions, worked out in the open: make-or-buy, bid scoring,
contract type. Pure functions over numbers a caller already has — nothing here
reads the store or a clock, so a what-if page can call these with values typed
into a form and never touch the database.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

ScopeCertainty = Literal["well_defined", "somewhat_defined", "poorly_defined"]
RiskAppetite = Literal["seller_bears_risk", "shared_risk", "buyer_bears_risk"]


@dataclass(frozen=True)
class MakeOrBuyResult:
    """The volume at which making and buying cost the same, and the call it implies.

    ``break_even_volume`` is ``None`` when making is never cheaper per unit — no
    volume, however large, closes a per-unit gap that runs the other way.
    """

    break_even_volume: float | None
    recommendation: Literal["make", "buy", "either"]
    reason: str


def make_or_buy(
    make_cost: float, buy_cost: float, volume: float, fixed_make_cost: float
) -> MakeOrBuyResult:
    """Break-even volume = the fixed cost of making divided by the per-unit saving.

    Below that many units the fixed cost of making is not yet paid back by the
    per-unit saving, so buying is cheaper; above it, making is. Every input must
    be non-negative — a cost or a volume cannot be typed as a negative number.
    """
    if make_cost < 0 or buy_cost < 0 or volume < 0 or fixed_make_cost < 0:
        raise ValueError("make_or_buy needs non-negative costs and volume")
    if make_cost >= buy_cost:
        return MakeOrBuyResult(
            None,
            "buy",
            "Making costs at least as much per unit as buying, so no volume makes "
            "making worthwhile.",
        )
    break_even = fixed_make_cost / (buy_cost - make_cost)
    if volume > break_even:
        return MakeOrBuyResult(
            break_even,
            "make",
            f"At {volume:g} units, above the break-even of {break_even:g}, making "
            "is cheaper than buying.",
        )
    if volume < break_even:
        return MakeOrBuyResult(
            break_even,
            "buy",
            f"At {volume:g} units, below the break-even of {break_even:g}, buying "
            "is cheaper than making.",
        )
    return MakeOrBuyResult(
        break_even,
        "either",
        f"At {volume:g} units, exactly the break-even, making and buying cost the same.",
    )


@dataclass(frozen=True)
class BidScore:
    """One proposal's weighted total."""

    vendor: str
    score: float


@dataclass(frozen=True)
class BidScoringResult:
    """The ranking, highest score first, and how it moves if a weight is dropped."""

    ranking: tuple[BidScore, ...]
    #: Per criterion, whether zeroing that weight (and re-normalising the rest)
    #: would change who ranks first — the ranking's sensitivity to that weight.
    sensitivity: dict[str, bool]


def _weighted_total(scores: Mapping[str, float], weights: Mapping[str, float]) -> float:
    return sum(scores.get(criterion, 0.0) * weight for criterion, weight in weights.items())


def bid_score(
    proposals: Mapping[str, Mapping[str, float]], criteria_weights: Mapping[str, float]
) -> BidScoringResult:
    """Score every proposal against ``criteria_weights`` and rank the totals.

    ``proposals`` maps a vendor's name to its scores per criterion (unscored
    criteria count as zero). Sensitivity is read by dropping one criterion's
    weight at a time and re-ranking on what remains: a criterion whose removal
    changes who ranks first is one the ranking depends on.
    """
    if not proposals:
        raise ValueError("bid_score needs at least one proposal")
    if not criteria_weights:
        raise ValueError("bid_score needs at least one weighted criterion")
    totals = {
        vendor: _weighted_total(scores, criteria_weights) for vendor, scores in proposals.items()
    }
    ranking = tuple(
        BidScore(vendor, round(total, 4))
        for vendor, total in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    )
    winner = ranking[0].vendor
    sensitivity: dict[str, bool] = {}
    for criterion in criteria_weights:
        remaining = {c: w for c, w in criteria_weights.items() if c != criterion}
        if not remaining:
            sensitivity[criterion] = False  # the only criterion — nothing to compare it against
            continue
        alt_totals = {
            vendor: _weighted_total(scores, remaining) for vendor, scores in proposals.items()
        }
        alt_winner = max(alt_totals, key=lambda vendor: alt_totals[vendor])
        sensitivity[criterion] = alt_winner != winner
    return BidScoringResult(ranking, sensitivity)


@dataclass(frozen=True)
class ContractTypeGuidance:
    """A recommended PMBOK contract type, and the one-sentence reason for it."""

    contract_type: Literal["fixed-price", "cost-reimbursable", "time-and-materials"]
    reason: str


def contract_type_guidance(
    scope_certainty: ScopeCertainty, risk_appetite: RiskAppetite
) -> ContractTypeGuidance:
    """Which PMBOK contract family fits, from how well the scope is known and who
    should carry the risk of it changing.

    Well-defined scope with the seller able to carry risk fixes a price; poorly
    defined scope, or a buyer willing to carry the risk itself, pays for actual
    cost instead; a partly defined scope with the risk shared fits neither
    extreme, so it is priced by the hour or unit instead of fixed or reimbursed.
    """
    if scope_certainty == "well_defined" and risk_appetite in (
        "seller_bears_risk",
        "shared_risk",
    ):
        return ContractTypeGuidance(
            "fixed-price",
            "The scope is defined well enough to fix a price, and the seller can "
            "be asked to carry the risk of overrunning it.",
        )
    if scope_certainty == "poorly_defined" or risk_appetite == "buyer_bears_risk":
        return ContractTypeGuidance(
            "cost-reimbursable",
            "The scope is not defined well enough to fix a price, or the buyer is "
            "willing to carry the risk of it changing, so the seller is paid for "
            "actual cost plus a fee.",
        )
    return ContractTypeGuidance(
        "time-and-materials",
        "The scope is only partly defined and the risk is shared, so paying by "
        "the hour or unit for a short, small engagement fits better than fixing "
        "a price or reimbursing cost.",
    )
