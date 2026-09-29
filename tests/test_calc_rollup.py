"""Rollup tests — one KPI set, computed the same way at every hierarchy level.

The weighting test is the important one: it is written so that a naive mean of
child percentages fails it, which is what keeps a $500 finished project from
outvoting a $500k barely-started one in portfolio health.
"""

from datetime import date
from decimal import Decimal

import pytest

from driftless.calc.rollup import Kpis, LeafMetrics, Node, on_track_share, roll_up

AS_OF = date(2026, 7, 21)


def leaf(
    name: str,
    budget: str,
    actual: str = "0",
    percent: str = "0",
    risks: int = 0,
    rag: str = "green",
    wip: int | None = None,
    throughput: int | None = None,
    cycle: float | None = None,
) -> Node:
    return Node(
        level="project",
        name=name,
        metrics=LeafMetrics(
            budget=Decimal(budget),
            actual_cost=Decimal(actual),
            percent_complete=Decimal(percent),
            open_high_risks=risks,
            rag=rag,  # type: ignore[arg-type]
            wip=wip,
            throughput_per_week=throughput,
            median_cycle_days=cycle,
        ),
    )


def test_leaf_rolls_up_to_its_own_metrics() -> None:
    kpis = roll_up(leaf("alpha", "1000", actual="250", percent="0.4", risks=2, rag="amber"), AS_OF)
    assert (kpis.budget, kpis.actual_cost, kpis.percent_complete) == (
        Decimal(1000),
        Decimal(250),
        Decimal("0.4"),
    )
    assert (kpis.open_high_risks, kpis.rag, kpis.leaf_count) == (2, "amber", 1)
    assert (kpis.level, kpis.name, kpis.as_of) == ("project", "alpha", AS_OF)


def test_percent_complete_is_budget_weighted_not_a_naive_mean() -> None:
    """A tiny finished project must not drag a huge unfinished one to 55%."""
    portfolio = Node(
        level="portfolio",
        name="brc",
        children=(leaf("big", "500000", percent="0.10"), leaf("tiny", "500", percent="1.00")),
    )
    pct = roll_up(portfolio, AS_OF).percent_complete
    assert pct < Decimal("0.15"), "naive mean of children would report ~0.55"
    assert pct.quantize(Decimal("0.00001")) == Decimal("0.10090")


def test_sums_and_worst_child_rag_win() -> None:
    portfolio = Node(
        level="portfolio",
        name="brc",
        children=(
            leaf("a", "100", actual="60", risks=1, rag="green"),
            leaf("b", "300", actual="10", risks=2, rag="red"),
            leaf("c", "600", actual="30", risks=0, rag="amber"),
        ),
    )
    kpis = roll_up(portfolio, AS_OF)
    assert (kpis.budget, kpis.actual_cost) == (Decimal(1000), Decimal(100))
    assert (kpis.open_high_risks, kpis.rag, kpis.leaf_count) == (3, "red", 3)
    assert tuple(child.name for child in kpis.children) == ("a", "b", "c")


def test_unknown_is_lowest_severity_and_only_wins_over_unknown() -> None:
    """A no-data child never drags a real verdict down: unknown is below green,
    so worst-of ignores it beside any measured status — but a branch whose
    children are *all* unknown has nothing to assess and stays unknown."""

    def worst(*rags: str) -> str:
        node = Node(
            level="portfolio",
            name="p",
            children=tuple(leaf(str(i), "1", rag=rag) for i, rag in enumerate(rags)),
        )
        return roll_up(node, AS_OF).rag

    assert worst("unknown", "green") == "green"
    assert worst("unknown", "amber") == "amber"
    assert worst("unknown", "red") == "red"
    assert worst("unknown", "unknown") == "unknown"
    # Behaviour-preserving for the pre-existing three-state cases.
    assert worst("green", "amber", "red") == "red"
    assert worst("green", "green") == "green"


def test_every_level_goes_through_the_same_code_path() -> None:
    """Rolling a program up standalone equals its rollup inside a portfolio."""
    program = Node(
        level="program",
        name="delivery",
        children=(leaf("a", "400", percent="0.25", rag="amber"), leaf("b", "1600", percent="0.75")),
    )
    portfolio = Node(level="portfolio", name="brc", children=(program,))
    standalone = roll_up(program, AS_OF)
    nested = roll_up(portfolio, AS_OF).children[0]
    assert standalone == nested
    # The portfolio above one program reports exactly what the program reports.
    top = roll_up(portfolio, AS_OF)
    assert (top.budget, top.percent_complete, top.rag) == (
        standalone.budget,
        standalone.percent_complete,
        standalone.rag,
    )
    assert top.percent_complete == Decimal("0.65")


def test_empty_node_does_not_explode() -> None:
    kpis = roll_up(Node(level="portfolio", name="empty"), AS_OF)
    assert (kpis.budget, kpis.actual_cost, kpis.percent_complete) == (
        Decimal(0),
        Decimal(0),
        Decimal(0),
    )
    # A childless branch has nothing to assess: unknown, never a false green.
    assert (kpis.open_high_risks, kpis.rag, kpis.leaf_count, kpis.children) == (0, "unknown", 0, ())


def test_zero_budget_subtree_falls_back_to_equal_weights() -> None:
    program = Node(
        level="program",
        name="internal",
        children=(leaf("a", "0", percent="1.0"), leaf("b", "0", percent="0.0")),
    )
    assert roll_up(program, AS_OF).percent_complete == Decimal("0.5")


def test_zero_budget_fallback_weights_per_leaf_across_unequal_depths() -> None:
    """The equal-weight fallback counts LEAVES, not immediate children: a lone
    leaf beside a 3-leaf program is 1 vote against 3, not a 50/50 split."""
    portfolio = Node(
        level="portfolio",
        name="internal",
        children=(
            leaf("solo", "0", percent="1.0"),
            Node(
                level="program",
                name="deep",
                children=tuple(leaf(f"p{i}", "0", percent="0.0") for i in range(3)),
            ),
        ),
    )
    assert roll_up(portfolio, AS_OF).percent_complete == Decimal("0.25")


def test_node_cannot_be_both_a_leaf_and_a_branch() -> None:
    with pytest.raises(ValueError, match="either"):
        Node(
            level="program", name="bad", metrics=leaf("x", "1").metrics, children=(leaf("y", "1"),)
        )


def test_leaf_metrics_reject_impossible_input() -> None:
    with pytest.raises(ValueError, match="negative"):
        leaf("x", "-1")
    with pytest.raises(ValueError, match="fraction"):
        leaf("x", "1", percent="1.5")
    with pytest.raises(ValueError, match="RAG"):
        leaf("x", "1", rag="puce")


def _projects(*rags: str) -> list[Kpis]:
    """Project-level KPIs carrying only the RAG verdict on-track share reads."""
    return [roll_up(leaf(str(i), "1", rag=rag), AS_OF) for i, rag in enumerate(rags)]


def test_on_track_share_all_green_is_100() -> None:
    assert on_track_share(_projects("green", "green")) == Decimal(100)


def test_on_track_share_none_green_is_zero() -> None:
    assert on_track_share(_projects("red", "amber")) == Decimal(0)


def test_on_track_share_is_none_when_there_are_no_projects() -> None:
    """No projects means nothing to be on track — the view renders this as "n/a"."""
    assert on_track_share([]) is None


def test_on_track_share_mixed_returns_the_exact_green_fraction() -> None:
    """Calc returns the precise share; rounding to a whole percent is the view's job."""
    share = on_track_share(_projects("green", "red", "amber"))
    assert share == Decimal(100) / 3
    assert f"{share:.0f}%" == "33%"


def test_a_leaf_with_no_agile_evidence_reports_flow_as_none() -> None:
    """A predictive project's leaf carries no flow figures at all — n/a, not 0."""
    kpis = roll_up(leaf("predictive", "100"), AS_OF)
    assert (kpis.wip, kpis.throughput_per_week, kpis.median_cycle_days) == (None, None, None)


def test_a_leaf_passes_its_own_flow_figures_through_unchanged() -> None:
    kpis = roll_up(leaf("agile", "100", wip=3, throughput=5, cycle=2.5), AS_OF)
    assert (kpis.wip, kpis.throughput_per_week, kpis.median_cycle_days) == (3, 5, 2.5)


def test_wip_and_throughput_sum_across_children() -> None:
    portfolio = Node(
        level="portfolio",
        name="brc",
        children=(
            leaf("a", "1", wip=2, throughput=3),
            leaf("b", "1", wip=4, throughput=1),
        ),
    )
    kpis = roll_up(portfolio, AS_OF)
    assert (kpis.wip, kpis.throughput_per_week) == (6, 4)


def test_wip_sum_skips_children_with_no_agile_evidence_rather_than_zeroing_them() -> None:
    """A mix of agile and predictive projects still sums the agile ones — the
    predictive sibling contributes nothing, but does not turn the sum into 0."""
    portfolio = Node(
        level="portfolio",
        name="brc",
        children=(leaf("agile", "1", wip=5, throughput=2), leaf("predictive", "1")),
    )
    kpis = roll_up(portfolio, AS_OF)
    assert (kpis.wip, kpis.throughput_per_week) == (5, 2)


def test_flow_is_none_when_no_child_has_any_agile_evidence() -> None:
    portfolio = Node(level="portfolio", name="brc", children=(leaf("a", "1"), leaf("b", "1")))
    kpis = roll_up(portfolio, AS_OF)
    assert (kpis.wip, kpis.throughput_per_week, kpis.median_cycle_days) == (None, None, None)


def test_median_cycle_days_is_a_throughput_weighted_mean() -> None:
    """Two projects, one finishing four times as much work per week as the
    other: its cycle time counts four times as heavily in the rollup mean."""
    portfolio = Node(
        level="portfolio",
        name="brc",
        children=(
            leaf("fast", "1", wip=1, throughput=8, cycle=1.0),
            leaf("slow", "1", wip=1, throughput=2, cycle=5.0),
        ),
    )
    kpis = roll_up(portfolio, AS_OF)
    # (8*1.0 + 2*5.0) / (8+2) = 18/10 = 1.8
    assert kpis.median_cycle_days == pytest.approx(1.8)


def test_median_cycle_days_excludes_a_child_with_zero_throughput_this_period() -> None:
    """A child that reports a cycle time but zero throughput this window
    contributes no weight — it cannot pull the mean toward its own figure."""
    portfolio = Node(
        level="portfolio",
        name="brc",
        children=(
            leaf("idle", "1", wip=1, throughput=0, cycle=99.0),
            leaf("active", "1", wip=1, throughput=3, cycle=2.0),
        ),
    )
    kpis = roll_up(portfolio, AS_OF)
    assert kpis.median_cycle_days == pytest.approx(2.0)


def test_leaf_metrics_reject_negative_flow_fields() -> None:
    with pytest.raises(ValueError, match="wip and throughput"):
        leaf("x", "1", wip=-1)
    with pytest.raises(ValueError, match="wip and throughput"):
        leaf("x", "1", throughput=-1)
    with pytest.raises(ValueError, match="median_cycle_days"):
        leaf("x", "1", cycle=-1.0)


def test_rollup_never_reads_the_wall_clock() -> None:
    tree = Node(level="portfolio", name="brc", children=(leaf("a", "10", percent="0.5"),))
    past = roll_up(tree, date(2020, 1, 1))
    future = roll_up(tree, date(2030, 1, 1))
    assert past.as_of == date(2020, 1, 1)
    assert future.as_of == date(2030, 1, 1)
    assert (past.budget, past.percent_complete) == (future.budget, future.percent_complete)
    with pytest.raises(TypeError):
        roll_up(tree)  # type: ignore[call-arg]
