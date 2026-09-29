"""The flow calculator: ``GET /projects/{project_id}/flow``.

The routed assistant (``assess.model.ASSISTANT_ROUTES``) for the schedule
knowledge area's ``agile_release_planning`` technique. Every figure comes from
``pmbok.flow_facts.flow_snapshot`` — the same adapter the project hub's flow
tile reads, so the two can never disagree — and reads no wall clock, so a
pinned as-of regenerates byte-identically. Burndown and burnup draw as inline
SVG polylines, the ``home.html`` S-curve's own idiom, each repeated as a data
table beside it (``gantt.html``'s text-twin rule: a reader gets nothing from a
``<polyline>``).

Cumulative flow draws as a stacked-area chart: N polygons, bottom-up, one per
band (done, in progress, not started). The stacking arithmetic — each band's
top and bottom boundary as a running total — happens here in Python, once,
rather than inside the template with Jinja's awkward mutable-state idiom;
the template only maps those already-stacked levels onto the same x/y scale
burndown and burnup use. Each band fills with a DIFFERENT rated token
(``--ink``/``--muted-ink``/``--muted-bg``, the same three ``gantt.html``
already uses for its own bars) and carries its own text label, so the bands
stay distinct in greyscale or print, not only by hue. The table stays the
text twin underneath, same as every other chart on this page.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.calc.flow import BurndownPoint, BurnupPoint, CumulativeFlowPoint, DurationStats
from driftless.models import Project
from driftless.pmbok import flow_facts
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES


def _duration(stats: DurationStats) -> dict[str, Any]:
    return {"count": stats.count, "median": stats.median, "p85": stats.p85}


def _burndown_rows(points: Sequence[BurndownPoint]) -> list[dict[str, Any]]:
    return [{"day": p.day.isoformat(), "remaining": p.remaining_points} for p in points]


def _burnup_rows(points: Sequence[BurnupPoint]) -> list[dict[str, Any]]:
    return [
        {"day": p.day.isoformat(), "completed": p.completed_points, "scope": p.scope_points}
        for p in points
    ]


def _cumulative_flow_rows(points: Sequence[CumulativeFlowPoint]) -> list[dict[str, Any]]:
    return [
        {
            "day": p.day.isoformat(),
            "not_started": p.not_started,
            "in_progress": p.in_progress,
            "done": p.done,
        }
        for p in points
    ]


def _cumulative_flow_levels(points: Sequence[CumulativeFlowPoint]) -> list[dict[str, int]]:
    """The three stacked-area band boundaries, bottom-up: ``done`` alone,
    ``wip`` (done + in progress), ``total`` (every item logged by that day).
    A band's own polygon fills between two of these — done between 0 and
    ``done``, in progress between ``done`` and ``wip``, not started between
    ``wip`` and ``total`` — so the three polygons tile exactly, no gap and no
    overlap."""
    return [
        {
            "done": p.done,
            "wip": p.done + p.in_progress,
            "total": p.done + p.in_progress + p.not_started,
        }
        for p in points
    ]


def _forecast_summary(band: Any) -> str:
    """One plain sentence a reader with no PMBOK background can act on."""
    if band is None:
        return "No completed sprint yet — there is nothing to forecast a release from."
    if band.likely is None:
        return "At this velocity, the remaining work never completes."
    return f"At the current pace, the likely completion date is {band.likely}."


def create_flow_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The per-project flow calculator page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/flow", response_class=HTMLResponse)
    def flow_page(
        request: Request, project_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        snap = flow_facts.flow_snapshot(db, project, at)
        context: dict[str, Any] = {
            "project": project,
            "as_of": at.isoformat(),
            "wip": snap.wip,
            "throughput": snap.throughput,
            "cycle_time": _duration(snap.cycle_time),
            "lead_time": _duration(snap.lead_time),
            "forecast": snap.forecast,
            "forecast_summary": _forecast_summary(snap.forecast),
            "active_sprint": snap.active_sprint,
            "burndown": _burndown_rows(snap.burndown),
            "burnup": _burnup_rows(snap.burnup),
            "cumulative_flow": _cumulative_flow_rows(snap.cumulative_flow),
            "cumulative_flow_levels": _cumulative_flow_levels(snap.cumulative_flow),
        }
        return TEMPLATES.TemplateResponse(request, "flow.html", context)

    return router
