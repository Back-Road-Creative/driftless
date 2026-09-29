from __future__ import annotations

import pytest

from driftless.calc.procurement import (
    bid_score,
    contract_type_guidance,
    make_or_buy,
)


def test_make_or_buy_recommends_make_above_break_even() -> None:
    # Break-even = 50_000 / (60 - 40) = 2_500 units.
    result = make_or_buy(make_cost=40.0, buy_cost=60.0, volume=3_000.0, fixed_make_cost=50_000.0)
    assert result.break_even_volume == pytest.approx(2_500.0)
    assert result.recommendation == "make"


def test_make_or_buy_recommends_buy_below_break_even() -> None:
    result = make_or_buy(make_cost=40.0, buy_cost=60.0, volume=1_000.0, fixed_make_cost=50_000.0)
    assert result.break_even_volume == pytest.approx(2_500.0)
    assert result.recommendation == "buy"


def test_make_or_buy_indifferent_at_break_even() -> None:
    result = make_or_buy(make_cost=40.0, buy_cost=60.0, volume=2_500.0, fixed_make_cost=50_000.0)
    assert result.recommendation == "either"


def test_make_or_buy_always_buy_when_making_is_never_cheaper() -> None:
    result = make_or_buy(make_cost=60.0, buy_cost=60.0, volume=10_000.0, fixed_make_cost=50_000.0)
    assert result.break_even_volume is None
    assert result.recommendation == "buy"


def test_make_or_buy_rejects_negative_inputs() -> None:
    with pytest.raises(ValueError, match="negative"):
        make_or_buy(make_cost=-1.0, buy_cost=60.0, volume=1.0, fixed_make_cost=1.0)


def test_bid_score_ranks_the_weighted_totals() -> None:
    result = bid_score(
        proposals={
            "Acme": {"price": 8.0, "quality": 6.0},
            "Bexley": {"price": 6.0, "quality": 9.0},
        },
        criteria_weights={"price": 0.6, "quality": 0.4},
    )
    assert result.ranking[0].vendor == "Acme"
    assert result.ranking[0].score == pytest.approx(0.6 * 8.0 + 0.4 * 6.0)
    assert result.ranking[1].vendor == "Bexley"


def test_bid_score_sensitivity_flags_a_weight_that_flips_the_winner() -> None:
    result = bid_score(
        proposals={
            "Acme": {"price": 8.0, "quality": 6.0},
            "Bexley": {"price": 6.0, "quality": 9.0},
        },
        criteria_weights={"price": 0.6, "quality": 0.4},
    )
    # Dropping "price" leaves quality alone, which favours Bexley — a flip.
    assert result.sensitivity["price"] is True


def test_bid_score_sensitivity_is_false_for_the_sole_criterion() -> None:
    """One criterion has nothing left to compare against once dropped, so its
    sensitivity reads False rather than raising on an empty weight mapping."""
    result = bid_score(
        proposals={"Acme": {"price": 8.0}, "Bexley": {"price": 6.0}},
        criteria_weights={"price": 1.0},
    )
    assert result.sensitivity == {"price": False}


def test_bid_score_requires_at_least_one_proposal_and_one_weight() -> None:
    with pytest.raises(ValueError, match="proposal"):
        bid_score(proposals={}, criteria_weights={"price": 1.0})
    with pytest.raises(ValueError, match="weighted criterion"):
        bid_score(proposals={"Acme": {"price": 1.0}}, criteria_weights={})


def test_contract_type_guidance_fixed_price_when_scope_is_clear() -> None:
    result = contract_type_guidance(
        scope_certainty="well_defined", risk_appetite="seller_bears_risk"
    )
    assert result.contract_type == "fixed-price"


def test_contract_type_guidance_cost_reimbursable_when_scope_is_unclear() -> None:
    result = contract_type_guidance(
        scope_certainty="poorly_defined", risk_appetite="seller_bears_risk"
    )
    assert result.contract_type == "cost-reimbursable"


def test_contract_type_guidance_time_and_materials_for_the_partial_middle() -> None:
    result = contract_type_guidance(scope_certainty="somewhat_defined", risk_appetite="shared_risk")
    assert result.contract_type == "time-and-materials"
