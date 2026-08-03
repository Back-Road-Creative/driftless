"""The home dashboard: a RAG heatmap over every portfolio, plus KPI tiles.

This module adapts and renders; it does not calculate. It builds its rollup tree
from ``driftless.report.gather`` — the same adapter the report engine uses — and
formats each row with ``gather.cell``, so a figure on the screen and the same
figure in a generated document are produced and formatted by identical code and
cannot disagree. The as-of date is a query parameter falling back to the default
handed to ``create_router``; nothing here reads the wall clock.

``home.html`` extends ``base.html`` for the shared nav (Dashboard | Threats |
Departments | PMBOK | Process map) and styling. calc carries
no ids: project ids, burns and freshness thread in from ``gather.leaf_projects``,
drill ids from ``gather.id_tree``. The rail renders ``attention_feed``'s order
VERBATIM (never re-ranked or re-filtered); threats sign off via ``/sign-off``.
Each rail item also carries its ``attention_trends`` week-over-week marker, the
same worked shape the threat board's trend uses -- annotation only, never a
re-rank."""

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from driftless.api.app import get_session
from driftless.assess import adapters
from driftless.assess.feed import attention_feed, attention_trends
from driftless.calc.rollup import Kpis, RagStatus, on_track_share
from driftless.models import CostEntry, Project, StatusSnapshot
from driftless.pmbok.rollup import business_completeness, business_process_cells
from driftless.report import gather
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

Db = Annotated[Session, Depends(get_session)]

BURN_SAMPLES = 10  # fixed number of AC sample dates per project burn sparkline
TREEMAP_W, TREEMAP_H = 340.0, 200.0  # the portfolio treemap's SVG canvas, in template units

FIX_PATHS = {"no_status": "status", "stale_status": "status", "low_completeness": "wizard"}


def _burn_series(project: Project, costs: list[CostEntry], as_of: date) -> dict[str, Any]:
    """One project's burn curve: cumulative actual cost against its flat budget.

    Plots ``AC(t)`` at up to ``BURN_SAMPLES`` :func:`gather.sample_dates` from
    the ``adapters.plan_baseline`` window's earliest planned start through
    ``as_of`` — genuinely time-phased, read straight from that project's dated
    ``CostEntry`` rows — with ``bac`` the constant budget of the same baseline
    (its top reference line). One selector, so the axis a bar is drawn against
    is the plan the bar's own BAC came from. The project is adapted ONCE through
    ``gather.snapshot_sweep`` (pinned byte-equal to ``adapters.snapshot_from``)
    and reused at every sample — pure in-memory work over the already
    eager-loaded project, so this whole sweep fires no query. A project with no
    APPROVED baseline has no plan to burn against and returns an empty
    ``points`` list, which the template renders as a dash."""
    baseline = adapters.plan_baseline(project)
    lines = baseline.lines if baseline else []
    if not lines:
        return {"bac": 0.0, "points": []}
    at = gather.snapshot_sweep(project, costs)
    starts = [line.planned_start for line in lines]
    points = [
        {"ac": round(at(sample).ac, 2)}
        for sample in gather.sample_dates(starts, as_of, BURN_SAMPLES)
    ]
    return {"bac": round(at(as_of).bac, 2), "points": points}


def _portfolio_rows(
    total: Kpis, ids: tuple[gather.IdTree, ...]
) -> list[tuple[str, Decimal, RagStatus, int]]:
    """Every portfolio across every business, flattened for the treemap: real
    name/BAC/RAG zipped against ``id_tree``'s parallel real-id shape (calc's
    ``Kpis`` carries no ids) -- both already computed by ``_render``, so this
    walks in-memory trees and fires no query of its own."""
    return [
        (portfolio.name, portfolio.budget, portfolio.rag, branch.id)
        for business, biz_ids in zip(total.children, ids, strict=True)
        for portfolio, branch in zip(business.children, biz_ids.children, strict=True)
    ]


def _render(request: Request, db: Session, as_of: date) -> HTMLResponse:
    """Roll every business up into the heatmap — every figure calc's, identical to
    the Portfolio Rollup document. Ids, burns and freshness thread leaf-for-leaf
    from ``gather.leaf_projects``; zero businesses render the onboarding CTA."""
    total = gather.overview(db, as_of)
    share = on_track_share(gather.leaves(total))
    costs = gather.project_costs(db)
    # Per-project status freshness: the taken_on of each project's most recent
    # StatusSnapshot on or before as_of, from one grouped max query — not one query
    # per project. A project that has never filed a status is simply absent from
    # the dict, so freshness.get(pid) is None and its row reads "never" (finding #19).
    freshness: dict[int, date] = {
        pid: taken_on
        for pid, taken_on in db.execute(
            select(StatusSnapshot.project_id, func.max(StatusSnapshot.taken_on))
            .where(StatusSnapshot.taken_on <= as_of)
            .group_by(StatusSnapshot.project_id)
        ).all()
    }
    # The rail: the canonical feed, order rendered verbatim; each runs ONCE here.
    feed = attention_feed(db, as_of)
    # Week-over-week trend per rail item, mirroring the threat board's marker
    # (``web.pages._trend_delta``). ``feed`` above is reused rather than
    # recomputed, so this fetches the prior week's feed exactly once more --
    # the feed runs twice total per render (current + prior), never per-item.
    trends = attention_trends(db, as_of, feed)
    completeness = business_completeness(business_process_cells(db, as_of))
    # Both fetched ONCE and reused below (burn rows, the business curve, the
    # treemap's ids) -- home already runs a fresh hierarchy query per gather
    # call, so this reuse adds no new one.
    all_projects = gather.leaf_projects(db)
    ids = gather.id_tree(db)
    curve = gather.business_curve(all_projects, costs, as_of)
    treemap = gather.treemap_layout(_portfolio_rows(total, ids), TREEMAP_W, TREEMAP_H)
    projects = iter(all_projects)
    businesses = 0
    rows: list[dict[str, Any]] = []
    for row in gather.table_rows(total.children, ids):
        if row["kind"] == "business":
            businesses += 1
            row["anchor"] = f"business-{businesses}"
        elif row["kind"] == "project":
            p = next(projects)
            burn = _burn_series(p, costs.get(p.id, []), as_of)
            row |= {"id": p.id, "burn": burn, "freshness": freshness.get(p.id)}
        rows.append(row)
    assert next(projects, None) is None, "leaf order drift: more projects than tree leaves"
    context = {
        "as_of": as_of.isoformat(),
        "heading": total.children[0].name if businesses == 1 else "Dashboard",
        "multi": businesses > 1,
        "total": gather.cell(total),
        "on_track": f"{share:.0f}%" if share is not None else "n/a",
        "threats_open": sum(1 for i in feed if i.kind == "threat"),
        "completeness": f"{completeness * 100:.0f}%" if completeness is not None else "n/a",
        "rail": feed,
        "trends": trends,
        "fix_paths": FIX_PATHS,
        "rows": rows,
        "curve": curve,
        "treemap": treemap,
        "treemap_w": TREEMAP_W,
        "treemap_h": TREEMAP_H,
    }
    return TEMPLATES.TemplateResponse(request, "home.html", context)


def create_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """A router serving ``GET /``, with the as-of date the caller wants by default.

    A callable default is resolved per request rather than once at mount time:
    a process that stays up for weeks must not keep serving the date it booted
    on. Passing a plain ``date`` pins the page to that date forever, which is
    what a reproducible report wants.
    """
    router = APIRouter(route_class=PageRoute)
    resolve = default_as_of if callable(default_as_of) else lambda: default_as_of

    @router.get("/", response_class=HTMLResponse)
    def home(request: Request, db: Db, as_of: date | None = None) -> HTMLResponse:
        return _render(request, db, as_of or resolve())

    return router
