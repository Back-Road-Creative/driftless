"""No new code may decide which baseline is the plan without saying "approved".

Five places in the package chose a baseline and one of them disagreed: the earned-value
adapter took the newest row of ANY status while the Gantt page, the capacity heatmap, the
PMBOK artifact map and the Scope & Baseline document took the newest *approved* one. The
odd one out was the one every EVM figure in the product flows through, so a draft nobody
approved printed BAC 4000 / CPI 5.00 next to a document saying the scope was unchanged.
Fixing that one call site closes the instance; this closes the class.

So the sites are *derived from the source*, never hand-listed: an AST walk over
``driftless/`` finds every scope that reads a project's ``baselines`` relationship or a
``Baseline`` row's ``version`` — the two ways to pick one plan out of several. Each must
either constrain status to ``"approved"`` or go through ``adapters.plan_baseline``, or
carry a written reason for needing neither — and the reasons are compared as an **exact
set**, so a new selection cannot quietly join them and a stale excuse fails just as loudly.
The evidence is read off the syntax tree, never the text: a docstring *saying* the word
approved is how a fresh unfiltered ``max()`` would otherwise slip past this file.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "driftless"
SELECTOR = "plan_baseline"  # driftless.assess.adapters.plan_baseline

# Scopes that touch a baseline version without choosing a plan, each with the reason it
# needs no status filter. Asserted as an exact set below.
NOT_CHOOSING_A_PLAN = {
    "driftless/assess/adapters.py:eager_project": (
        "loader options, not a query: it names Project.baselines to declare HOW the "
        "cascade is fetched. It selects no version — plan_baseline picks from what it "
        "loads, and must keep seeing every version to pick the newest approved one"
    ),
    "driftless/report/documents/scope_baseline.py:_baseline_view": (
        "renders one baseline it is HANDED. Its caller, render(), does the choosing and "
        "already filters on approved status; a second filter here would be a second rule"
    ),
    # gather.business_curve was the last residual here: it set the business S-curve's
    # x-axis from the newest baseline of any status. "A draft moves no number, it only
    # stretches the axis" turned out to be false — a sample before the plan begins earns
    # nothing, so the stretched axis WAS zero points on the curve. It now calls the
    # selector, and no longer reads a project's baselines at all, so it is not a site.
    "driftless/wizard/cli.py:_next_baseline_version": (
        "picks the next version number to WRITE, not the plan to read. It must see every "
        "existing version, approved or not, or it would hand back a number already taken "
        "and collide with the (project_id, version) unique constraint"
    ),
}

_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)


def _filters_on_approval(nodes: list[ast.AST]) -> bool:
    """``Baseline.status == "approved"``, ``status="approved"``, or a call to the shared
    selector. Real nodes only — a mention inside a docstring proves nothing."""
    return any(
        (isinstance(n, ast.Constant) and n.value == "approved")
        or (isinstance(n, ast.Name) and n.id == SELECTOR)
        or (isinstance(n, ast.Attribute) and n.attr == SELECTOR)
        for n in nodes
    )


def _own_nodes(scope: ast.AST) -> list[ast.AST]:
    """Every node in ``scope`` that is not inside a nested function, so each site is
    attributed to the innermost scope that actually writes it."""
    own, stack = [], [scope]
    while stack:
        node = stack.pop()
        own.append(node)
        stack.extend(c for c in ast.iter_child_nodes(node) if not isinstance(c, _FUNC))
    return own


def _picks_a_baseline(nodes: list[ast.AST]) -> bool:
    """Reads a project's ``baselines`` collection, or a ``Baseline`` row's ``version``."""
    attrs = {n.attr for n in nodes if isinstance(n, ast.Attribute)}
    names = {n.id for n in nodes if isinstance(n, ast.Name)}
    return "baselines" in attrs or ("version" in attrs and "Baseline" in (names | attrs))


def _scopes(path: Path) -> list[tuple[str, list[ast.AST]]]:
    """Every function in ``path`` plus its module body, each with only its OWN nodes."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    scopes = [(f.name, _own_nodes(f)) for f in ast.walk(tree) if isinstance(f, _FUNC)]
    body = [n for n in tree.body if not isinstance(n, _FUNC)]
    return [*scopes, ("<module>", [w for n in body for w in ast.walk(n)])]


def selection_sites() -> dict[str, list[ast.AST]]:
    """``path:scope`` -> its nodes, for every scope that chooses among baselines."""
    return {
        f"{path.relative_to(PACKAGE.parent)}:{name}": nodes
        for path in sorted(PACKAGE.rglob("*.py"))
        for name, nodes in _scopes(path)
        if _picks_a_baseline(nodes)
    }


def test_the_walk_finds_the_call_sites_it_exists_to_guard() -> None:
    """A walk that silently found nothing would pass this file forever."""
    sites = selection_sites()
    assert "driftless/assess/adapters.py:plan_baseline" in sites, sorted(sites)
    assert "driftless/web/gantt.py:gantt" in sites, sorted(sites)
    assert "driftless/pmbok/mapping.py:_approved_baseline" in sites, sorted(sites)


def test_every_baseline_selection_filters_on_approval_or_states_why_not() -> None:
    unfiltered = {
        site for site, nodes in selection_sites().items() if not _filters_on_approval(nodes)
    }
    assert unfiltered == set(NOT_CHOOSING_A_PLAN), (
        f"{sorted(unfiltered - set(NOT_CHOOSING_A_PLAN))} pick a baseline without "
        "constraining it to an approved one, so an unapproved draft becomes the plan there "
        "— call driftless.assess.adapters.plan_baseline, or write down here why this scope "
        f"is not choosing a plan. Stale reasons: {sorted(set(NOT_CHOOSING_A_PLAN) - unfiltered)}"
    )
    assert all(len(reason) > 60 for reason in NOT_CHOOSING_A_PLAN.values())


def test_the_earned_value_engine_reaches_the_plan_through_the_shared_selector() -> None:
    """The site this file exists for: the one engine every EVM figure flows through must
    not choose for itself, and the selector it defers to must still filter."""
    assert "driftless/assess/adapters.py:snapshot_from" not in NOT_CHOOSING_A_PLAN
    adapters = dict(_scopes(PACKAGE / "assess" / "adapters.py"))
    assert any(isinstance(n, ast.Name) and n.id == SELECTOR for n in adapters["snapshot_from"])
    assert _filters_on_approval(adapters[SELECTOR])
