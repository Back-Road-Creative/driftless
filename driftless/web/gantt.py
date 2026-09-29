"""The project schedule as bars on a timeline: ``GET /projects/{id}/gantt``.

Server-rendered inline SVG, the idiom ``status_form.html``'s charts set, so the page
draws with JavaScript off. Every coordinate is a pure function of stored rows and the
explicit as-of — the newest APPROVED baseline's planned windows, each task's
``percent_complete``, each milestone's ``target_date`` — over a window that always
contains the as-of, so the "today" rule IS the as-of, nothing reads a wall clock, and a
pinned as-of regenerates byte-identically. Colour carries nothing a reader needs
(progress is the filled LENGTH plus a printed percentage), and every bar and mark
repeats as a table row, because a screen reader gets nothing from a ``<rect>``. No
approved baseline means no schedule to draw: the shared empty state, not an empty grid.
Routed at ``/gantt`` because the bare ``/projects/{id}`` is the JSON read, registered
first and always winning the match; ``tests/test_web_routes_not_shadowed.py`` asserts
that for every page route, so no page can ship shadowed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased, selectinload

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.assess.adapters import approved_as_of
from driftless.models import (
    Baseline,
    BaselineLine,
    Milestone,
    Project,
    ProjectCalendar,
    Task,
    TaskDependency,
    Workstream,
)
from driftless.pmbok import risk_facts
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

# The drawing box, in the 320-wide user units status_form.html's charts use: a gutter for
# task names, a row per bar, a diamond half-diagonal for a milestone mark.
GUTTER, RIGHT, TOP, ROW, MARK = 92.0, 284.0, 22.0, 18.0, 6.0
# Bit 0 = Monday .. bit 6 = Sunday, matching ``ProjectCalendar.working_days`` itself.
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _x(day: date, first: date, span: int) -> float:
    """``day``'s place on the timeline, rounded — so a refetch is byte-identical."""
    return round(GUTTER + (day - first).days / span * (RIGHT - GUTTER), 1)


def _diamond(x: float, y: float) -> str:
    """A milestone mark, top vertex first so its date reads straight off the points."""
    return f"{x},{y - MARK} {round(x + MARK, 1)},{y} {x},{y + MARK} {round(x - MARK, 1)},{y}"


def schedule(
    lines: Sequence[BaselineLine], milestones: Sequence[Milestone], as_of: date
) -> dict[str, Any]:
    """Bars, milestone marks and the as-of rule — pure, from stored rows and the as-of,
    which joins the dates scaled across so the rule is always in view and there is one
    scale, never a special case for an as-of outside the plan."""
    days = [day for line in lines for day in (line.planned_start, line.planned_finish)]
    days += [milestone.target_date for milestone in milestones] + [as_of]
    first, span = min(days), max((max(days) - min(days)).days, 1)
    bars = []
    for index, line in enumerate(lines):  # the filled length is width x percent: the
        left = _x(line.planned_start, first, span)  # template's, so it stays derived
        width = round(max(_x(line.planned_finish, first, span) - left, 2.0), 1)
        bars.append({"line": line, "x": left, "y": round(TOP + index * ROW, 1), "width": width})
    band = round(TOP + len(bars) * ROW + MARK, 1)
    return {
        "bars": bars,
        "marks": [
            {"milestone": ms, "points": _diamond(_x(ms.target_date, first, span), band)}
            for ms in milestones
        ],
        "today": _x(as_of, first, span),
        "height": round(band + ROW, 1),
    }


def _working_days_label(mask: int) -> str:
    """The plain-language calendar note: which weekdays a mask names as working."""
    days = [name for bit, name in enumerate(_WEEKDAYS) if mask & (1 << bit)]
    return ", ".join(days) if days else "no working days"


def _dependencies(db: Session, project_id: int) -> list[dict[str, Any]]:
    """Every dependency edge inside ``project_id``, predecessor/successor NAMES already
    joined in — one statement, never a query per edge — ordered by successor then
    predecessor so a refetch is byte-identical."""
    predecessor, successor = aliased(Task), aliased(Task)
    rows = db.execute(
        select(predecessor.name, successor.name, TaskDependency.kind, TaskDependency.lag_days)
        .join(predecessor, TaskDependency.predecessor_task_id == predecessor.id)
        .join(successor, TaskDependency.successor_task_id == successor.id)
        .join(Workstream, successor.workstream_id == Workstream.id)
        .where(Workstream.project_id == project_id)
        .order_by(successor.name, predecessor.name)
    )
    return [{"predecessor": p, "successor": s, "kind": k, "lag_days": lag} for p, s, k, lag in rows]


def create_gantt_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The per-project schedule page, defaulting to ``default_as_of`` per request."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/gantt", response_class=HTMLResponse)
    def gantt(
        request: Request, project_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        # The newest approved version's lines in ONE query — the scalar subquery keeps a
        # re-baselined project from drawing two versions at once, and selectinload batches
        # every line's task into the same round trip instead of a query per row. Gated on
        # `at` through the shared adapters.approved_as_of, so a later approval cannot
        # repaint a page already rendered for an earlier as-of.
        approved = (
            Baseline.project_id == project.id,
            Baseline.status == "approved",
            approved_as_of(at),
        )
        newest = select(func.max(Baseline.version)).where(*approved).scalar_subquery()
        lines = db.scalars(
            select(BaselineLine)
            .join(Baseline)
            .where(*approved, Baseline.version == newest)
            .order_by(BaselineLine.planned_start, BaselineLine.task_id)
            .options(selectinload(BaselineLine.task))
        ).all()
        milestones = db.scalars(
            select(Milestone)
            .where(Milestone.project_id == project.id)
            .order_by(Milestone.target_date, Milestone.id)
        ).all()
        view = schedule(lines, milestones, at) if lines else None
        # One more statement each, both O(1) in the schedule's size: every dependency
        # edge inside this project (names joined in, never a query per edge) and the
        # project's own calendar, if it has one — the same "batched, never per-row"
        # rule ``lines``/``milestones`` above already follow.
        dependencies = _dependencies(db, project.id) if view else []
        calendar = (
            db.scalar(
                select(ProjectCalendar)
                .where(ProjectCalendar.project_id == project.id)
                .order_by(ProjectCalendar.id)
            )
            if view
            else None
        )
        calendar_note = (
            f"{calendar.name} ({_working_days_label(calendar.working_days)})" if calendar else None
        )
        # 11.6 propagation: the schedule-day impact of every filed risk response,
        # summed across the open register — the same figure the risk-response
        # planner reads, never a second computation. This codebase draws no
        # critical path, so the note names the whole register's impact rather
        # than a critical-path-only subset.
        risk_schedule_days = risk_facts.gather(db, project, at).responded_schedule_days
        context = {
            "project": project,
            "as_of": at.isoformat(),
            "view": view,
            "dependencies": dependencies,
            "calendar_note": calendar_note,
            "risk_schedule_days": risk_schedule_days,
        }
        return TEMPLATES.TemplateResponse(request, "gantt.html", context)

    return router
