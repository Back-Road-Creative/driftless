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

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.deps import Db
from driftless.assess.adapters import approved_as_of
from driftless.assess.evaluators import resource
from driftless.models import Baseline, BaselineLine, Person, Task
from driftless.web.as_of import as_of_dependency
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
# ORDER is the legend's order — least loaded first, then the reading no ratio produces —
# so the key reads as a scale rather than as four unrelated washes.
_WASHES = {"under": "", "tight": "st-warn", "over": "st-bad", "unknown": "st-muted"}


def _percent(ratio: float) -> str:
    """A ratio as a whole-number percentage. ONE spelling, so the figure a cell prints
    and the threshold the legend names are the same arithmetic, never two roundings."""
    return f"{round(ratio * 100)}%"


def legend() -> list[dict[str, str]]:
    """The key, BUILT from ``_WASHES`` and the evaluator's own ratios rather than written.

    A legend is a second copy of the classification rule, and this one had drifted: it
    printed 100-120% as "near cap" and over 120% as "overloaded" while ``capacity_cell``
    has called anything over ``_RED_RATIO`` (1.0) over since it was written. Deriving it
    is the only version of this that cannot say something the grid does not do."""
    amber, red = _percent(resource._AMBER_RATIO), _percent(resource._RED_RATIO)
    reach = {
        "under": f"up to {amber} of capacity — the bar\u2019s length is the share",
        "tight": f"over {amber} and up to {red} of capacity",
        "over": f"over {red} of capacity",
        "unknown": "no weekly capacity recorded, so no share can be taken",
    }
    return [{"state": s, "wash": w, "reach": reach[s]} for s, w in _WASHES.items()]


def _approved(as_of: date) -> Any:
    """WHEN a task's hours fall; version last, so the fold below keeps the newest. Gated
    on ``as_of`` through the shared ``adapters.approved_as_of``, so a version approved
    after ``as_of`` cannot book capacity for a render at that as-of — the same rule
    :func:`plan_baseline` already applies for EVM, not a second one for this page."""
    return (
        select(BaselineLine, Baseline.version)
        .join(Baseline)
        .where(Baseline.status == "approved", approved_as_of(as_of))
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


def hours_label(value: float) -> str:
    """A stable hours string — one decimal at most, no trailing ``.0``, no minus zero.

    Public: ``web.assist_department`` reuses this for its demand-versus-capacity
    figures, so an hours string never reads differently on the two pages."""
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


def capacity_cell(hours: float, capacity: float) -> dict[str, str]:
    """One person-week (#1635) — the evaluator's thresholds, and its skip where there is no
    capacity to weigh against: ``unknown``, never a 0% that looks fine.

    Public: ``web.assist_department`` reuses this SAME classification for its
    demand-versus-capacity rows, rather than restating the red/amber thresholds
    a second time."""
    if capacity <= 0:
        state = "unknown"
    elif hours / capacity > resource._RED_RATIO:
        state = "over"
    elif hours / capacity > resource._AMBER_RATIO:
        state = "tight"
    else:
        state = "under"
    mark = "" if state == "under" else state  # the word a shade cannot carry, printed as text
    ratio = hours / capacity if capacity > 0 else 0.0
    return {
        "hours": hours_label(hours),
        "state": state,
        "mark": mark,
        "wash": _WASHES[state],
        # The SHARE, twice over, because a wash alone was imperceptible below the amber
        # threshold: every cell from 0% to 80% of capacity painted identically, so the
        # heat lived in the hours column and nowhere in the picture. ``percent`` is text
        # (it survives greyscale, a colour-blind reader and forced-colours, where a fill
        # is dropped); ``fill`` is the same number as a bar LENGTH, clamped at the cell
        # so an over-capacity ratio cannot draw past its own box. Empty percent for
        # ``unknown``: there is no capacity to take a share of, and printing 0% there is
        # exactly the "looks fine" reading this page refuses above.
        "percent": "" if state == "unknown" else _percent(ratio),
        "fill": _percent(min(ratio, 1.0)),
    }


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
        row: Row = {
            "name": person.name,
            "kind": person.kind,
            "cells": [capacity_cell(hours, cap) for hours in booked],
        }
        row["capacity"] = hours_label(cap) if cap > 0 else "not recorded"
        row["unplaced"], row["total"] = hours_label(total - sum(booked)), hours_label(total)
        rows.append(row)
    return rows


def assignments(session: Session, as_of: date) -> list[Assignment]:
    """Every task the evaluator counts, windowed by its newest approved line as of
    ``as_of`` — ONE query, folded per task so a re-baselined project books its hours once."""
    approved = _approved(as_of)
    plan = approved.c
    rows = session.execute(
        select(Task.id, Task.assignee_id, Task.estimate, plan.planned_start, plan.planned_finish)
        .outerjoin(approved, plan.task_id == Task.id)
        .where(Task.assignee_id.is_not(None), *resource._OPEN_HOUR_TASK)
        .order_by(Task.id, plan.version)
    )
    folded: dict[int, Assignment] = {}
    for task_id, person_id, estimate, start, finish in rows:
        assert person_id is not None  # narrows what the WHERE already guarantees
        folded[task_id] = (person_id, estimate or 0.0, (start, finish) if start else None)
    return [folded[task_id] for task_id in sorted(folded)]


def _task_window(session: Session, as_of: date, task_id: int) -> Window:
    """``task_id``'s planned window off its newest approved baseline line visible at
    ``as_of`` — the SAME gate :func:`assignments` reads, for a task that may carry no
    assignee yet (``assignments`` itself only reads tasks that already have one, so
    it cannot answer this for a task a clash preview is about to propose one for)."""
    approved = _approved(as_of)
    plan = approved.c
    row = session.execute(
        select(plan.planned_start, plan.planned_finish)
        .where(plan.task_id == task_id)
        .order_by(plan.version.desc())
    ).first()
    if row is None or row.planned_start is None:
        return None
    return (row.planned_start, row.planned_finish)


def clash_preview(
    session: Session, as_of: date, person_id: int, task_id: int, weeks: int = HORIZON_WEEKS
) -> dict[str, Any] | None:
    """The clash a proposed assignment WOULD cause, before any write: ``person_id``'s
    own heatmap row as it stands, and as it would read with ``task_id``'s estimate
    added to it — the SAME ``allocation``/``capacity_cell`` this page's grid draws,
    so a preview can never disagree with the grid it previews. No auto-levelling: the
    caller decides whether to file the assignment anyway.

    ``None`` when either id names nothing this store holds, the task carries no
    estimate (nothing would change), or it has no planned window yet (nowhere on the
    grid to place it) — the same "there is nothing to preview" reading the rest of
    this module gives a horizon or capacity it cannot weigh.
    """
    person = session.get(Person, person_id)
    task = session.get(Task, task_id)
    if person is None or task is None or not task.estimate:
        return None
    if task.estimate_unit != "hours" or task.status == "done":
        return None  # the same _OPEN_HOUR_TASK reading assignments() itself is gated on
    window = _task_window(session, as_of, task_id)
    if window is None:
        return None
    span = weeks_from(as_of, weeks)
    current_loads = [row for row in assignments(session, as_of) if row[0] == person_id]
    proposed_loads = [*current_loads, (person_id, task.estimate, window)]
    current = allocation([person], current_loads, span)[0]
    proposed = allocation([person], proposed_loads, span)[0]
    newly_over = any(
        after["state"] == "over" and before["state"] != "over"
        for before, after in zip(current["cells"], proposed["cells"], strict=True)
    )
    return {
        "person": person.name,
        "task": task.name,
        "weeks": [week.isoformat() for week in span],
        "current": current,
        "proposed": proposed,
        "would_overallocate": newly_over,
    }


def create_heatmap_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The whole-business capacity grid, defaulting to ``default_as_of`` per request."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/org/heatmap", response_class=HTMLResponse)
    def heatmap(
        request: Request,
        db: Db,
        weeks: Horizon = HORIZON_WEEKS,
        at: date = Depends(resolve_as_of),
    ) -> HTMLResponse:
        # ``weeks`` is bounded in its own type, so an out-of-range address is refused by
        # request validation before a query runs — the designed 404, never a quiet clamp.
        span = weeks_from(at, weeks)
        loads = assignments(db, at)  # one query for the assignments, one for the people below,
        order = (Person.name, Person.id)  # never one per person, per week or per horizon
        people = db.scalars(select(Person).order_by(*order)).all() if loads else []
        columns = [week.isoformat() for week in span]  # off the as-of, never a clock
        context = {
            "as_of": at.isoformat(),
            "weeks": columns,
            "rows": allocation(people, loads, span),
            "horizon": weeks,
            "horizons": HORIZON_CHOICES,
            "legend": legend(),
        }
        return TEMPLATES.TemplateResponse(request, "heatmap.html", context)

    return router
