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

from collections.abc import Sequence
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
    """Measured facts on a leaf. `percent_complete` is a fraction in 0..1."""

    budget: Decimal
    actual_cost: Decimal
    percent_complete: Decimal
    open_high_risks: int
    rag: RagStatus

    def __post_init__(self) -> None:
        if self.budget < 0 or self.actual_cost < 0 or self.open_high_risks < 0:
            raise ValueError("budget, actual cost and risk counts cannot be negative")
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
    """The KPI set. Identical shape at every level, hence one dashboard tile row."""

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
