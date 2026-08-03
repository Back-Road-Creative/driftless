"""Rollup edges where "no data" must not read as "healthy" (audit F-C6, F-C7).

Two lies with one root: treating the absence of a verdict as a verdict. A
childless branch used to roll up green, so an empty portfolio rendered healthy
on the heatmap while an empty *project* correctly read unknown; and
``on_track_share`` counted unknown projects in its denominator, so a store with
no verdict at all printed "0% on track" as though every project were failing.
"""

from datetime import date
from decimal import Decimal

from driftless.calc.rollup import Kpis, LeafMetrics, Node, on_track_share, roll_up

AS_OF = date(2026, 7, 21)


def _leaf(name: str, rag: str) -> Node:
    return Node(
        level="project",
        name=name,
        metrics=LeafMetrics(
            budget=Decimal(1),
            actual_cost=Decimal(0),
            percent_complete=Decimal(0),
            open_high_risks=0,
            rag=rag,  # type: ignore[arg-type]
        ),
    )


def _projects(*rags: str) -> list[Kpis]:
    return [roll_up(_leaf(str(i), rag), AS_OF) for i, rag in enumerate(rags)]


def test_an_empty_portfolio_rolls_up_unknown_not_green() -> None:
    """A childless branch has nothing to assess — same answer an empty project
    gives. Green here would render an empty portfolio healthy on the heatmap."""
    assert roll_up(Node(level="portfolio", name="empty"), AS_OF).rag == "unknown"


def test_an_empty_program_inside_a_rated_portfolio_is_unknown_but_never_drags() -> None:
    """The empty branch reads unknown on its own tile, and — unknown being the
    lowest severity — the parent's real verdict still wins the roll-up."""
    portfolio = Node(
        level="portfolio",
        name="brc",
        children=(Node(level="program", name="empty"), _leaf("real", "green")),
    )
    kpis = roll_up(portfolio, AS_OF)
    assert kpis.children[0].rag == "unknown"
    assert kpis.rag == "green"


def test_on_track_share_is_none_when_every_project_is_unknown() -> None:
    """4 unrated projects used to print "0% on track" — a claim about verdicts
    the store never made. None tells the caller to render n/a instead."""
    assert on_track_share(_projects("unknown", "unknown", "unknown", "unknown")) is None


def test_on_track_share_excludes_unknown_from_the_denominator() -> None:
    """3 unknown + 1 green is 100% of what is assessable, not 25% of everything."""
    assert on_track_share(_projects("unknown", "unknown", "unknown", "green")) == Decimal(100)
    assert on_track_share(_projects("unknown", "unknown", "green", "red")) == Decimal(50)
