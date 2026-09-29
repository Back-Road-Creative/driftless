"""Hierarchy rollups — the same KPI set computed at every level.

One function, `roll_up`, level-parameterized by the node it is handed. A
portfolio, a program and a project all travel the identical code path, so a
number shown on a drill-down page cannot disagree with the number above it.

Two rules worth stating out loud, because getting either wrong misreports
health:

- **Percent complete is weighted by budget**, never averaged. An unweighted
  mean lets a $500 finished project outvote a $500k barely-started one. When a
  subtree's total budget is zero the weights are all zero and a budget-weighted
  average is undefined; the fallback is equal weight per leaf, which is the
  only defensible reading of "every child counts the same amount of nothing".
  A node with no leaves at all reports 0.
- **RAG rolls up worst-child-wins** (red beats amber beats green). A portfolio
  is not green while a project under it is red. A fourth state, ``unknown``
  (derived, never stored), marks *nothing to assess*: a leaf with no baseline,
  milestones or status snapshots, and equally a childless branch — an empty
  portfolio must not render healthy. It carries the lowest severity, so a real
  verdict always wins worst-of over it (``[unknown, green] -> green``); a
  branch is unknown only when childless or when its children all are.

Pure functions, no I/O. Time enters only through the explicit `as_of` argument
— nothing here reads the wall clock, which is what makes a rollup reproducible
from the same inputs forever.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal, get_args

__all__ = ["RAG_SEVERITY", "Kpis", "LeafMetrics", "Node", "RagStatus", "on_track_share", "roll_up"]

RagStatus = Literal["unknown", "green", "amber", "red"]

# Worst-wins ordering: the max severity among children becomes the parent's.
# ``unknown`` (nothing to assess) sits below green, so a real status always wins.
# Canonical severity ranking for a ``RagStatus`` — the single source of truth.
# ``driftless.assess.model.SEVERITY_WEIGHT`` derives from this mapping rather
# than re-declaring it, so the two layers cannot disagree on ordering.
RAG_SEVERITY: dict[RagStatus, int] = {"unknown": -1, "green": 0, "amber": 1, "red": 2}
_RAG_SEVERITY = RAG_SEVERITY  # thin alias so the internal call site below is unchanged


@dataclass(frozen=True, slots=True)
class LeafMetrics:
    """Measured facts on a leaf. `percent_complete` is a fraction in 0..1.

    The three flow fields (`wip`, `throughput_per_week`, `median_cycle_days`)
    are `None` for a leaf with no agile evidence — a predictive project, or an
    agile one with no backlog items yet — never a false zero: `None` rolls up
    to `None` when every child has nothing to report, and the dashboard reads
    that as "n/a", not "no work in progress". A default of `None` on every
    field makes this an additive change: every existing caller that built a
    `LeafMetrics` before flow existed keeps constructing one unchanged.
    """

    budget: Decimal
    actual_cost: Decimal
    percent_complete: Decimal
    open_high_risks: int
    rag: RagStatus
    wip: int | None = None
    throughput_per_week: int | None = None
    median_cycle_days: float | None = None

    def __post_init__(self) -> None:
        if self.budget < 0 or self.actual_cost < 0 or self.open_high_risks < 0:
            raise ValueError("budget, actual cost and risk counts cannot be negative")
        if (self.wip is not None and self.wip < 0) or (
            self.throughput_per_week is not None and self.throughput_per_week < 0
        ):
            raise ValueError("wip and throughput_per_week cannot be negative")
        if self.median_cycle_days is not None and self.median_cycle_days < 0:
            raise ValueError("median_cycle_days cannot be negative")
        if not Decimal(0) <= self.percent_complete <= Decimal(1):
            raise ValueError("percent_complete is a fraction in 0..1")
        if self.rag not in get_args(RagStatus):
            raise ValueError(f"unknown RAG status: {self.rag!r}")


@dataclass(frozen=True, slots=True)
class Node:
    """A level in the hierarchy: a leaf carrying metrics, or a branch of nodes.

    `level` is a free label ("portfolio", "program", "project", "task") — it is
    carried onto the result, never branched on, so adding a level needs no
    change here.
    """

    level: str
    name: str
    metrics: LeafMetrics | None = None
    children: tuple[Node, ...] = ()

    def __post_init__(self) -> None:
        if self.metrics is not None and self.children:
            raise ValueError("a node is either a leaf (metrics) or a branch (children)")


@dataclass(frozen=True, slots=True)
class Kpis:
    """The KPI set. Identical shape at every level, hence one dashboard tile row.

    `wip` and `throughput_per_week` sum: a portfolio's work in progress is the
    work in progress under it, and the same for throughput. `median_cycle_days`
    does not sum — cycle time is a duration, not a count — so it rolls up as a
    throughput-weighted MEAN of the children that report one, a documented
    approximation of the true pooled median: the tree carries each child's own
    already-summarized median, never the raw per-item durations a real pooled
    median would need. All three are `None` when no child (or, at a leaf,
    nothing measured) has agile evidence to report — the dashboard's `n/a`,
    never a false zero.
    """

    level: str
    name: str
    as_of: date
    budget: Decimal
    actual_cost: Decimal
    percent_complete: Decimal
    open_high_risks: int
    rag: RagStatus
    leaf_count: int
    children: tuple[Kpis, ...] = field(default=())
    wip: int | None = None
    throughput_per_week: int | None = None
    median_cycle_days: float | None = None


def roll_up(node: Node, as_of: date) -> Kpis:
    """Compute the KPI set for `node` and, recursively, for each child.

    `as_of` is stamped on every result and must be supplied by the caller; this
    module never reads the current date.
    """
    if node.metrics is not None:
        m = node.metrics
        return Kpis(
            level=node.level,
            name=node.name,
            as_of=as_of,
            budget=m.budget,
            actual_cost=m.actual_cost,
            percent_complete=m.percent_complete,
            open_high_risks=m.open_high_risks,
            rag=m.rag,
            leaf_count=1,
            wip=m.wip,
            throughput_per_week=m.throughput_per_week,
            median_cycle_days=m.median_cycle_days,
        )

    children = tuple(roll_up(child, as_of) for child in node.children)
    budget = sum((c.budget for c in children), Decimal(0))
    leaf_count = sum(c.leaf_count for c in children)
    return Kpis(
        level=node.level,
        name=node.name,
        as_of=as_of,
        budget=budget,
        actual_cost=sum((c.actual_cost for c in children), Decimal(0)),
        percent_complete=_weighted_percent(children, budget, leaf_count),
        open_high_risks=sum(c.open_high_risks for c in children),
        rag=_worst_rag(children),
        leaf_count=leaf_count,
        children=children,
        wip=_sum_optional(c.wip for c in children),
        throughput_per_week=_sum_optional(c.throughput_per_week for c in children),
        median_cycle_days=_weighted_cycle_days(children),
    )


def on_track_share(projects: Sequence[Kpis]) -> Decimal | None:
    """Share of assessable `projects` rated green, as a percentage in 0..100.

    "On track" is a count over calc's own RAG verdicts — the one figure the view
    would otherwise have to derive itself. Callers pass the project-level KPIs
    they want measured; this function never walks a tree or assumes a depth. The
    exact fraction is returned, not a rounded one: how many decimals to show is
    the view's decision. An ``unknown`` project carries no verdict, so it sits
    outside both numerator and denominator — counting it in the denominator made
    a store of wholly-unrated projects print "0% on track", a claim about
    verdicts nobody issued. `None` means nothing is assessable (no projects, or
    none with a verdict) — the home dashboard renders that as "n/a".
    """
    assessable = [p for p in projects if p.rag != "unknown"]
    if not assessable:
        return None
    green = sum(1 for p in assessable if p.rag == "green")
    return Decimal(green * 100) / len(assessable)


def _weighted_percent(children: tuple[Kpis, ...], budget: Decimal, leaf_count: int) -> Decimal:
    """Budget-weighted mean, falling back to equal-per-leaf when budget is zero."""
    if budget > 0:
        return sum((c.budget * c.percent_complete for c in children), Decimal(0)) / budget
    if leaf_count > 0:
        weighted = sum((c.leaf_count * c.percent_complete for c in children), Decimal(0))
        return weighted / Decimal(leaf_count)
    return Decimal(0)


def _sum_optional(values: Iterable[int | None]) -> int | None:
    """Sum the values that report something; `None` only when NONE of them do
    — the same "nothing to assess" reading `_worst_rag` gives a childless or
    all-unknown branch, applied to a flow count instead of a verdict."""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _weighted_cycle_days(children: tuple[Kpis, ...]) -> float | None:
    """Throughput-weighted mean cycle time over the children that report BOTH
    a throughput and a cycle time — see the `Kpis` docstring for why this is a
    documented approximation of a true pooled median rather than the median
    itself. A child with a cycle time but zero throughput this period
    contributes nothing to the weighted sum and is excluded, the same as it
    would be from a rate-weighted average anywhere else in the codebase."""
    weighted = [
        (c.median_cycle_days, c.throughput_per_week)
        for c in children
        if c.median_cycle_days is not None and c.throughput_per_week
    ]
    if not weighted:
        return None
    total_weight = sum(weight for _, weight in weighted)
    return sum(days * weight for days, weight in weighted) / total_weight


def _worst_rag(children: tuple[Kpis, ...]) -> RagStatus:
    """Highest-severity child wins; a childless branch has *nothing to assess*
    and is unknown, never green — an empty portfolio must give the same answer
    an empty project does, not render healthy on the heatmap. Because
    ``unknown`` is the lowest severity, worst-of is identical to the old
    green-upgrade loop for any mix of green/amber/red, while a branch whose
    children are *all* unknown rolls up unknown rather than a false green."""
    if not children:
        return "unknown"
    return max((child.rag for child in children), key=lambda rag: _RAG_SEVERITY[rag])
