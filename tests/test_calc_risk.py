"""Tests for the risk-analysis calculation core.

Worked examples are hand-computed so a reviewer can check them without running
anything: the EMV/decision-tree figures are the textbook well-vs-no-well case,
the P x I matrix is checked for totality (every level pair lands in a band),
and the simulation is checked for determinism and for monotonicity — adding a
risk to a register must never lower the p90 of total exposure.
"""

from __future__ import annotations

import pytest

from driftless.calc.forecast import Risk
from driftless.calc.risk import (
    DEFAULT_IMPACT_SCALE,
    DEFAULT_MATRIX,
    DEFAULT_PROBABILITY_SCALE,
    DecisionBranch,
    InfluenceEdge,
    InfluenceNode,
    Outcome,
    RiskBreakdownStructureCategory,
    SensitivityFactor,
    ThreePointEstimate,
    band_for,
    decision_tree,
    expected_monetary_value,
    influence_diagram,
    score,
    sensitivity,
    simulate_exposure,
)


def test_the_default_matrix_bands_every_level_pair() -> None:
    for probability_level in DEFAULT_PROBABILITY_SCALE.levels:
        for impact_level in DEFAULT_IMPACT_SCALE.levels:
            value, band = score(probability_level.name, impact_level.name)
            assert band in ("low", "moderate", "high")
    assert len(DEFAULT_MATRIX) == 25  # 5 probability levels x 5 impact levels


def test_a_worked_matrix_cell() -> None:
    # very_high x very_high is index 5 x 5 = 25, the matrix's own top band.
    value, band = score("very_high", "very_high")
    assert value == 25
    assert band == "high"
    value, band = score("very_low", "very_low")
    assert value == 1
    assert band == "low"


def test_score_refuses_an_unknown_level() -> None:
    with pytest.raises(ValueError, match="no matrix entry"):
        score("astronomical", "very_high")


def test_band_for_refuses_a_score_past_the_highest_band() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        band_for(9_999)


def test_a_risk_scale_finds_the_level_a_value_falls_in() -> None:
    level = DEFAULT_PROBABILITY_SCALE.level_for(0.45)
    assert level.name == "moderate"


def test_a_risk_scale_refuses_a_value_outside_every_level() -> None:
    with pytest.raises(ValueError, match="outside"):
        DEFAULT_PROBABILITY_SCALE.level_for(-0.1)


def test_every_rbs_category_carries_a_plain_summary() -> None:
    for category in RiskBreakdownStructureCategory:
        assert category.summary  # non-empty for every member, none silently blank


def test_three_point_estimate_pert_and_triangular_means() -> None:
    # Textbook figures: optimistic 4, most likely 6, pessimistic 14.
    estimate = ThreePointEstimate(optimistic=4.0, most_likely=6.0, pessimistic=14.0)
    assert estimate.pert_mean == pytest.approx((4 + 4 * 6 + 14) / 6)  # 7.0
    assert estimate.triangular_mean == pytest.approx((4 + 6 + 14) / 3)  # 8.0
    assert estimate.pert_std_dev == pytest.approx((14 - 4) / 6)  # 1.6667


def test_three_point_estimate_refuses_an_out_of_order_triple() -> None:
    with pytest.raises(ValueError, match="optimistic"):
        ThreePointEstimate(optimistic=10.0, most_likely=6.0, pessimistic=14.0)


REGISTER = (
    Risk("vendor slip", probability=0.4, impact=10_000.0),
    Risk("scope creep", probability=0.3, impact=20_000.0),
    Risk("key departure", probability=0.1, impact=50_000.0),
)


def test_simulate_exposure_is_deterministic_for_the_same_seed() -> None:
    first = simulate_exposure(REGISTER, iterations=500, seed=7)
    second = simulate_exposure(REGISTER, iterations=500, seed=7)
    assert first == second


def test_simulate_exposure_p90_does_not_fall_when_a_risk_is_added() -> None:
    baseline = simulate_exposure(REGISTER, iterations=2_000, seed=7)
    extra = REGISTER + (Risk("new supplier", probability=0.6, impact=5_000.0),)
    grown = simulate_exposure(extra, iterations=2_000, seed=7)
    assert grown.p90 >= baseline.p90


def test_simulate_exposure_refuses_zero_iterations() -> None:
    with pytest.raises(ValueError, match="iterations"):
        simulate_exposure(REGISTER, iterations=0, seed=1)


def test_simulate_exposure_refuses_a_probability_outside_zero_one() -> None:
    # Risk itself is the guard: it validates on construction, never at simulate time.
    with pytest.raises(ValueError, match="probability"):
        Risk("bad", probability=1.5, impact=100.0)


def test_expected_monetary_value_worked_example() -> None:
    # Classic decision-tree case: drill a well, 40% strike worth 700,000, 60% dry hole worth -100,000.
    outcomes = (Outcome(0.4, 700_000.0), Outcome(0.6, -100_000.0))
    assert expected_monetary_value(outcomes) == pytest.approx(220_000.0)


def test_expected_monetary_value_refuses_probabilities_not_summing_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        expected_monetary_value((Outcome(0.4, 1.0), Outcome(0.4, 2.0)))


def test_decision_tree_picks_the_higher_emv_branch() -> None:
    drill = DecisionBranch("drill", (Outcome(0.4, 700_000.0), Outcome(0.6, -100_000.0)))
    dont_drill = DecisionBranch("do not drill", (Outcome(1.0, 0.0),))
    result = decision_tree((drill, dont_drill))
    assert drill.emv == pytest.approx(220_000.0)
    assert dont_drill.emv == 0.0
    assert result.best is drill


def test_decision_tree_refuses_an_empty_set_of_branches() -> None:
    with pytest.raises(ValueError, match="branch"):
        decision_tree(())


def test_sensitivity_orders_the_largest_swing_first() -> None:
    factors = (
        SensitivityFactor("labour rate", low=180_000.0, high=220_000.0),  # swing 40,000
        SensitivityFactor("material cost", low=90_000.0, high=310_000.0),  # swing 220,000
        SensitivityFactor("schedule slip", low=195_000.0, high=205_000.0),  # swing 10,000
    )
    tornado = sensitivity(base=200_000.0, factors=factors)
    assert [row.name for row in tornado] == ["material cost", "labour rate", "schedule slip"]
    assert tornado[0].swing == pytest.approx(220_000.0)


def test_sensitivity_refuses_an_empty_set_of_factors() -> None:
    with pytest.raises(ValueError, match="factor"):
        sensitivity(base=0.0, factors=())


def test_influence_diagram_assembles_nodes_and_edges() -> None:
    nodes = (
        InfluenceNode("drill", "decision", "Drill the well?"),
        InfluenceNode("strike", "chance", "Strikes oil"),
        InfluenceNode("payoff", "value", "Net value"),
    )
    edges = (InfluenceEdge("drill", "payoff"), InfluenceEdge("strike", "payoff"))
    diagram = influence_diagram(nodes, edges)
    assert diagram.nodes == nodes
    assert diagram.edges == edges


def test_influence_diagram_refuses_an_unknown_node_kind() -> None:
    with pytest.raises(ValueError, match="kind"):
        influence_diagram((InfluenceNode("x", "outcome", "bad kind"),), ())


def test_influence_diagram_refuses_a_dangling_edge() -> None:
    nodes = (InfluenceNode("drill", "decision", "Drill the well?"),)
    with pytest.raises(ValueError, match="unknown node"):
        influence_diagram(nodes, (InfluenceEdge("drill", "nowhere"),))
