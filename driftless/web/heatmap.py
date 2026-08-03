"""Who is over capacity, and in which week: ``GET /org/heatmap``.

ONE definition of allocation, not two: this page IMPORTS ``assess.evaluators.resource``'s
``_OPEN_HOUR_TASK`` filter and its ``_AMBER_RATIO``/``_RED_RATIO`` thresholds rather than
restate them, so a row total is what ``person_task_loads`` returns for the same store; all that
is new is the spread, the evaluator having no time axis. The README carries the rest of the
design, each rule sitting on its code; ``/org`` because the bare paths are the CRUD API's."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.app import Db
from driftless.assess.evaluators import resource
from driftless.models import Baseline, BaselineLine, Person, Task
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

HORIZON_WEEKS = 6
# The far edge ``?weeks=N`` may reach. Half a year: past it an approved baseline plans
# almost nothing, so the extra columns are zeros bought at the full render price — and the
# price is the point. A column is a ``<th>`` plus one ``<td>`` per person, so an unbounded
# N is a denial of service written into our own dashboard's address bar. ONE constant, read
# by the route's bound and by ``weeks_from``, so no caller reaches a second, looser limit.
MAX_HORIZON_WEEKS = 26
HORIZON_CHOICES = (4, HORIZON_WEEKS, 13, MAX_HORIZON_WEEKS)  # month, default, quarter, ceiling
Horizon = Annotated[int, Query(ge=1, le=MAX_HORIZON_WEEKS)]
Window = tuple[date, date] | None
Assignment = tuple[int, float, Window]  # (assignee id, hours, planned window)
Row = dict[str, Any]
_WASHES = {"over": "st-bad", "tight": "st-warn", "unknown": "st-muted", "under": ""}
_APPROVED = (  # WHEN a task's hours fall; version last, so the fold below keeps the newest
    select(BaselineLine, Baseline.version).join(Baseline).where(Baseline.status == "approved")
).subquery()


def weeks_from(as_of: date, horizon: int = HORIZON_WEEKS) -> list[date]:
    """The Mondays the columns are: the as-of's OWN week first, ``horizon`` of them.

    A horizon outside 1..``MAX_HORIZON_WEEKS`` RAISES rather than clamping into range: the
    caller asked for a grid this page cannot draw, and silently handing back a different
    one is how a number nobody asked for gets read as the answer. The route declares the
    same bound, so its readers meet the refusal page instead of ever reaching this.
    """
    if not 1 <= horizon <= MAX_HORIZON_WEEKS:
        raise ValueError(f"horizon must be 1..{MAX_HORIZON_WEEKS} weeks, not {horizon}")
    monday = as_of - timedelta(days=as_of.weekday())
    return [monday + timedelta(days=7 * n) for n in range(horizon)]


def _hours(value: float) -> str:
    """A stable hours string — one decimal at most, no trailing ``.0``, no minus zero."""
    return f"{round(value, 1) or 0.0}".removesuffix(".0")


def _spread(estimate: float, window: Window, weeks: Sequence[date]) -> list[float]:
    """``estimate`` over ``weeks`` by the days ``window`` overlaps each — evenly, a task
    recording a total, not a curve. No window: real hours the store cannot place in a week."""
    if window is None:
        return [0.0] * len(weeks)
    start, finish = window
    days = (finish - start).days + 1
    shared = [(min(finish, w + timedelta(days=6)) - max(start, w)).days + 1 for w in weeks]
    return [estimate * max(overlap, 0) / days for overlap in shared]


def _cell(hours: float, capacity: float) -> dict[str, str]:
    """One person-week (#1635) — the evaluator's thresholds, and its skip where there is no
    capacity to weigh against: ``unknown``, never a 0% that looks fine."""
    if capacity <= 0:
        state = "unknown"
    elif hours / capacity > resource._RED_RATIO:
        state = "over"
    elif hours / capacity > resource._AMBER_RATIO:
        state = "tight"
    else:
        state = "under"
    mark = "" if state == "under" else state  # the word a shade cannot carry, printed as text
    return {"hours": _hours(hours), "state": state, "mark": mark, "wash": _WASHES[state]}


def allocation(people: Sequence[Person], load: Sequence[Assignment], span: list[date]) -> list[Row]:
    """The person x week grid — pure, from stored rows and the weeks handed in."""
    placed: dict[int, list[float]] = {person.id: [0.0] * len(span) for person in people}
    carried: dict[int, float] = dict.fromkeys(placed, 0.0)
    for person_id, estimate, window in load:
        carried[person_id] += estimate
        for index, hours in enumerate(_spread(estimate, window, span)):
            placed[person_id][index] += hours
    rows = []
    for person in people:
        cap, booked, total = person.capacity_hours, placed[person.id], carried[person.id]
        row: Row = {"name": person.name, "cells": [_cell(hours, cap) for hours in booked]}
        row["capacity"] = _hours(cap) if cap > 0 else "not recorded"
        row["unplaced"], row["total"] = _hours(total - sum(booked)), _hours(total)
        rows.append(row)
    return rows


def assignments(session: Session) -> list[Assignment]:
    """Every task the evaluator counts, windowed by its newest approved line — ONE query,
    folded per task so a re-baselined project books its hours once."""
    plan = _APPROVED.c
    rows = session.execute(
        select(Task.id, Task.assignee_id, Task.estimate, plan.planned_start, plan.planned_finish)
        .outerjoin(_APPROVED, plan.task_id == Task.id)
        .where(Task.assignee_id.is_not(None), *resource._OPEN_HOUR_TASK)
        .order_by(Task.id, plan.version)
    )
    folded: dict[int, Assignment] = {}
    for task_id, person_id, estimate, start, finish in rows:
        assert person_id is not None  # narrows what the WHERE already guarantees
        folded[task_id] = (person_id, estimate or 0.0, (start, finish) if start else None)
    return [folded[task_id] for task_id in sorted(folded)]


def create_heatmap_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The whole-business capacity grid, defaulting to ``default_as_of`` per request."""
    router = APIRouter(route_class=PageRoute)
    resolve = default_as_of if callable(default_as_of) else lambda: default_as_of

    @router.get("/org/heatmap", response_class=HTMLResponse)
    def heatmap(
        request: Request, db: Db, as_of: date | None = None, weeks: Horizon = HORIZON_WEEKS
    ) -> HTMLResponse:
        # ``weeks`` is bounded in its own type, so an out-of-range address is refused by
        # request validation before a query runs — the designed 404, never a quiet clamp.
        span = weeks_from(at := as_of or resolve(), weeks)
        loads = assignments(db)  # one query for the assignments, one for the people below,
        order = (Person.name, Person.id)  # never one per person, per week or per horizon
        people = db.scalars(select(Person).order_by(*order)).all() if loads else []
        columns = [week.isoformat() for week in span]  # off the as-of, never a clock
        context = {
            "as_of": at.isoformat(),
            "weeks": columns,
            "rows": allocation(people, loads, span),
            "horizon": weeks,
            "horizons": HORIZON_CHOICES,
        }
        return TEMPLATES.TemplateResponse(request, "heatmap.html", context)

    return router
