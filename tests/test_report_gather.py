"""gather's leaf RAG folds the assessment rollup with milestone status.

The home dashboard and every rollup read the leaf ``gather`` builds, so a
milestone-only verdict would show green for a project the assessment engine
rates red. A project whose milestone is MET (milestone-green) but whose cost is
red (CPI < 0.9) must therefore surface as a red leaf, matching the threat board.
"""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.calc.rollup import Kpis, Node
from driftless.db import Base, new_engine, new_session_factory
from driftless.report import gather

AS_OF = date(2026, 3, 31)
JAN = date(2026, 1, 31)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


def _leaf(nodes: tuple[Node, ...], name: str) -> Node:
    for portfolio in nodes:
        for project in portfolio.children:
            if project.name == name:
                return project
    raise AssertionError(f"no leaf {name!r}")


def test_milestone_slip_days_is_the_one_helper_schedule_and_forecast_share() -> None:
    """No baseline date -> undefined slip; a baseline date -> the day-count between
    it and target, positive when late, negative when early -- the Schedule and
    Forecast documents both read this instead of each computing their own."""
    unbaselined = m.Milestone(name="ship", target_date=AS_OF)
    assert gather.milestone_slip_days(unbaselined) is None

    late = m.Milestone(name="ship", target_date=AS_OF, baseline_date=JAN)
    assert gather.milestone_slip_days(late) == (AS_OF - JAN).days

    early = m.Milestone(name="ship", target_date=JAN, baseline_date=AS_OF)
    assert gather.milestone_slip_days(early) == (JAN - AS_OF).days


def test_cost_red_milestone_met_project_is_a_red_leaf(db: Session) -> None:
    """MET milestone, but CPI = EV 500 / AC 700 = 0.71 -> the leaf is cost-red."""
    portfolio = m.Portfolio(name="Content Brands", business=m.Business(name="BRC"))
    project = m.Project(name="Rigscore", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="Rigscore", project=project)
    task = m.Task(name="Rigscore", workstream=stream, estimate_unit="hours", percent_complete=50)
    baseline = m.Baseline(project=project, version=1, status="approved")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
    line.planned_start, line.planned_finish = JAN, AS_OF
    db.add(line)
    db.add(m.Milestone(project=project, name="ship", target_date=AS_OF, status="met"))
    db.add(m.CostEntry(project=project, category="labour", incurred_on=JAN, amount=700.0))
    db.commit()

    leaf = _leaf(gather.portfolio_nodes(db, AS_OF), "Rigscore")
    assert leaf.metrics is not None
    assert leaf.metrics.rag == "red", "milestone-met but cost-red must fold to red"


def test_business_nodes_scope_programs_and_direct_projects(db: Session) -> None:
    """Businesses never merge; programs nest; program-less projects stay direct."""
    brands = m.Portfolio(name="Brands", business=m.Business(name="Acme"))
    video = m.Program(name="Video", portfolio=brands)
    db.add(m.Project(name="GMS", portfolio=brands, program=video))
    db.add(m.Project(name="Solo", portfolio=brands))
    db.add(m.Portfolio(name="Ventures", business=m.Business(name="Zephyr")))
    db.commit()

    acme, zephyr = gather.business_nodes(db, AS_OF)
    assert (acme.name, zephyr.name) == ("Acme", "Zephyr")
    assert [p.name for p in zephyr.children] == ["Ventures"], "portfolios stay business-scoped"
    (pf,) = acme.children
    assert [(c.level, c.name) for c in pf.children] == [("program", "Video"), ("project", "Solo")]
    assert [c.name for c in pf.children[0].children] == ["GMS"]
    assert [p.name for p in gather.leaf_projects(db)] == ["GMS", "Solo"], "tree leaf order"


def test_a_project_under_a_foreign_program_fails_loudly(db: Session) -> None:
    """A project whose program lives in ANOTHER portfolio has no bucket the
    grouped walk ever yields, so it used to vanish silently from every rollup
    surface (heatmap, table rows, treemap, leaf thread) while the direct
    Project queries still showed it. A pre-existing bad row must fail loudly."""
    home = m.Portfolio(name="Home", business=m.Business(name="BRC"))
    away = m.Portfolio(name="Away", business=m.Business(name="Other"))
    video = m.Program(name="Video", portfolio=home)
    stray = m.Project(name="Stray", portfolio=away, program=video)  # bypasses the API gate
    db.add(stray)
    db.commit()

    with pytest.raises(RuntimeError) as caught:
        gather.business_nodes(db, AS_OF)
    assert f"project {stray.id}" in str(caught.value), "the message must name the project"
    assert f"program {video.id}" in str(caught.value), "and the foreign program"
    with pytest.raises(RuntimeError):
        gather.leaf_projects(db)


def test_a_program_attached_project_is_counted_not_vanished(db: Session) -> None:
    """Regression pin for the silent-vanish half of the same bug: a project in a
    same-portfolio program must appear in the overview leaf count and rows."""
    home = m.Portfolio(name="Home", business=m.Business(name="BRC"))
    video = m.Program(name="Video", portfolio=home)
    db.add(m.Project(name="Housed", portfolio=home, program=video))
    db.commit()

    kpis = gather.overview(db, AS_OF)
    assert kpis.leaf_count == 1, "a program-attached project is a counted leaf"
    assert "Housed" in [row["name"] for row in gather.table_rows(kpis.children)]


def test_project_with_nothing_to_assess_is_an_unknown_leaf(db: Session) -> None:
    """No baseline (BAC 0), no milestones and no status snapshots means there is
    nothing to assess. The leaf must read unknown/no-data, not a colour that
    implies a verdict — an empty project is not a mildly-concerning amber one."""
    portfolio = m.Portfolio(name="Internal", business=m.Business(name="BRC"))
    db.add(m.Project(name="Empty Placeholder", portfolio=portfolio, delivery_mode="predictive"))
    db.commit()

    leaf = _leaf(gather.portfolio_nodes(db, AS_OF), "Empty Placeholder")
    assert leaf.metrics is not None
    assert leaf.metrics.rag == "unknown", "a project with nothing to assess is no-data, not amber"


def _kpis(level: str, name: str, children: tuple[Kpis, ...] = ()) -> Kpis:
    return Kpis(level, name, AS_OF, Decimal(0), Decimal(0), Decimal(0), 0, "green", 0, children)


def _drill_tree() -> tuple[Kpis, ...]:
    """Two businesses, each with one portfolio, so both id counters exercise a
    real depth-first count rather than always landing on 1."""
    video = _kpis("program", "Video", (_kpis("project", "GMS"),))
    brands = _kpis("portfolio", "Brands", (video, _kpis("project", "Solo")))
    second = _kpis("portfolio", "Second", (_kpis("program", "Only"),))
    return (
        _kpis("business", "Acme", (brands,)),
        _kpis("business", "Zephyr", (second,)),
    )


def _drill_ids() -> tuple[gather.IdTree, ...]:
    """Real DB ids in ``_drill_tree``'s exact shape, deliberately NOT positional."""
    brands = gather.IdTree(7, (gather.IdTree(9, (gather.IdTree(4),)), gather.IdTree(5)))
    second = gather.IdTree(3, (gather.IdTree(8),))
    return (gather.IdTree(1, (brands,)), gather.IdTree(2, (second,)))


def test_table_rows_stamps_real_db_ids_from_the_id_tree() -> None:
    rows = {row["name"]: row for row in gather.table_rows(_drill_tree(), _drill_ids())}
    assert (rows["Brands"]["id"], rows["Second"]["id"]) == (7, 3), "portfolios carry real ids"
    assert (rows["Video"]["id"], rows["Only"]["id"]) == (9, 8), "programs carry real ids"
    assert (rows["Acme"]["id"], rows["Solo"]["id"]) == (1, 5), "business and project rows too"
    assert "id" not in gather.table_rows(_drill_tree())[0], "no ids without the tree (documents)"


def test_find_node_matches_by_real_id_and_returns_the_id_subtree() -> None:
    tree, ids = _drill_tree(), _drill_ids()
    found = gather.find_node(tree, ids, "portfolio", 3)
    assert found is not None and found[0] is tree[1].children[0] and found[1] is ids[1].children[0]
    assert gather.find_node(tree, ids, "portfolio", 99) is None, "an absent id is a clean miss"


def _baselined(db: Session, name: str, cost: float, start: date, finish: date) -> m.Project:
    """One project with a single baselined task -- ``business_curve``'s raw input."""
    portfolio = m.Portfolio(name=name, business=m.Business(name=f"BRC {name}"))
    project = m.Project(name=name, portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name=name, project=project)
    task = m.Task(name=name, workstream=stream, estimate_unit="hours", percent_complete=0)
    baseline = m.Baseline(project=project, version=1, status="approved")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=cost)
    line.planned_start, line.planned_finish = start, finish
    db.add(line)
    return project


def test_business_curve_sums_planned_and_actual_across_projects(db: Session) -> None:
    """Two projects, staggered windows and spend. Hand-computed at the FIRST
    sample (the earlier project's own start -- exactly 1/31 of its plan
    accrued, the later project not yet started) and the LAST sample (as-of,
    both fully accrued and every cost entry counted)."""
    a = _baselined(db, "A", 3100.0, date(2026, 1, 1), date(2026, 1, 31))
    db.add(m.CostEntry(project=a, category="labour", incurred_on=date(2026, 1, 1), amount=500.0))
    db.add(m.CostEntry(project=a, category="labour", incurred_on=date(2026, 2, 1), amount=700.0))
    b = _baselined(db, "B", 3000.0, date(2026, 2, 1), date(2026, 3, 2))
    db.add(m.CostEntry(project=b, category="labour", incurred_on=date(2026, 2, 1), amount=200.0))
    db.commit()

    projects = gather.leaf_projects(db)
    costs = gather.project_costs(db)
    curve = gather.business_curve(projects, costs, AS_OF)

    assert len(curve["points"]) == 12
    assert curve["points"][0] == {"date": "2026-01-01", "pv": 100.0, "ac": 500.0}, (
        "only A has accrued plan/spend on day 1, dated at the earlier project's own start"
    )
    assert curve["points"][-1] == {"date": AS_OF.isoformat(), "pv": 6100.0, "ac": 1400.0}, (
        "both fully accrued by as-of, and the last sample IS as-of"
    )
    assert gather.business_curve(projects, costs, AS_OF) == curve, "pure: same inputs, same output"


def test_business_curve_with_nothing_baselined_is_empty(db: Session) -> None:
    """No project at all, or a project with no baseline: both read as empty."""
    stub = m.Portfolio(name="Internal", business=m.Business(name="BRC"))
    db.add(m.Project(name="Bare", portfolio=stub, delivery_mode="predictive"))
    db.commit()
    projects = gather.leaf_projects(db)
    assert gather.business_curve(projects, gather.project_costs(db), AS_OF) == {"points": []}
    assert gather.business_curve((), {}, AS_OF) == {"points": []}


def test_business_curve_never_samples_past_as_of(db: Session) -> None:
    """A project whose earliest baselined start is still in the future must not
    push the curve's sample dates past ``as_of``: the old span clamp collapsed
    every sample onto that future start date itself -- which is AFTER as_of --
    so a chart "as of AS_OF" was counting a cost entry dated after AS_OF."""
    future_start = date(2026, 5, 1)
    project = _baselined(db, "Future", 3000.0, future_start, date(2026, 5, 31))
    db.add(
        m.CostEntry(project=project, category="labour", incurred_on=date(2026, 4, 15), amount=999.0)
    )
    db.commit()

    projects = gather.leaf_projects(db)
    curve = gather.business_curve(projects, gather.project_costs(db), AS_OF)

    assert curve["points"], "a baselined project still produces points"
    assert all(p == {"date": AS_OF.isoformat(), "pv": 0.0, "ac": 0.0} for p in curve["points"]), (
        "every sample must clamp to as_of: PV is 0 (the plan has not started as "
        "of as_of) and the cost entry dated between as_of and the future start "
        "must never be counted"
    )


def test_treemap_layout_areas_are_proportional_to_bac() -> None:
    rows: list[tuple[str, Decimal, str, int]] = [
        ("Alpha", Decimal("1000"), "green", 11),
        ("Beta", Decimal("3000"), "amber", 12),
        ("Gamma", Decimal("6000"), "red", 13),
    ]
    rects = gather.treemap_layout(rows, 400.0, 200.0)
    total_area, total_bac = 400.0 * 200.0, 10_000.0
    for rect, (_, bac, _, _) in zip(rects, rows, strict=True):
        assert rect.w * rect.h == pytest.approx(float(bac) / total_bac * total_area)


def test_treemap_layout_keeps_given_order_and_carries_real_ids() -> None:
    rows: list[tuple[str, Decimal, str, int]] = [
        ("Z", Decimal("100"), "green", 9),
        ("A", Decimal("200"), "red", 3),
    ]
    rects = gather.treemap_layout(rows, 300.0, 150.0)
    assert [r.name for r in rects] == ["Z", "A"], (
        "row order preserved -- never resorted (no squarify)"
    )
    assert [r.id for r in rects] == [9, 3]


def test_treemap_layout_gives_a_zero_bac_portfolio_a_visible_sliver() -> None:
    rows: list[tuple[str, Decimal, str, int]] = [
        ("Real", Decimal("5000"), "green", 1),
        ("Empty", Decimal("0"), "unknown", 2),
    ]
    rects = gather.treemap_layout(rows, 400.0, 200.0)
    empty = next(r for r in rects if r.name == "Empty")
    assert empty.w > 0 and empty.h > 0, "a zero-BAC portfolio still renders a clickable sliver"


def test_treemap_layout_is_deterministic_and_handles_no_rows() -> None:
    rows: list[tuple[str, Decimal, str, int]] = [("A", Decimal("100"), "green", 1)]
    assert gather.treemap_layout(rows, 300.0, 150.0) == gather.treemap_layout(rows, 300.0, 150.0)
    assert gather.treemap_layout([], 300.0, 150.0) == []
