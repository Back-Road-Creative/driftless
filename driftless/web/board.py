"""The task board: ``GET /projects/{project_id}/board`` — every task in its status column.

**The columns ARE the vocabulary.** ``columns`` seeds one bucket per entry of
``models.TASK_STATUSES`` and files each task into the bucket its own status names, so a
status added to the model becomes a column with nobody editing the template, one removed
stops rendering, and the order is the vocabulary's (already workflow order). A status
outside it cannot arrive — the table's CHECK forbids the row — and would raise here rather
than render a task into nothing. ``tests/test_web_board.py`` asserts the rendered set
against the tuple itself, so the derivation is pinned rather than merely intended.

**What a card shows**: name, workstream, assignee, percent complete, estimate and —
when it is not zero — how many tasks it waits for, from ``TaskDependency`` batched
into one grouped count query rather than a lazy load per card. Enough to pick the
next thing up or see who to ask. Left off deliberately: dates (a task carries none;
the planned window lives on the approved baseline the *Schedule* page draws), money
(the hub's earned value owns it) and RAID (the hub's too) — a board that grew those would
be a second project hub with worse layout.

**Blocked is not a colour.** Every card prints its own status as text, so "blocked" reads
in greyscale, out of column context and to a screen reader — hue is never the only carrier
(#1635). The one wash is a base.html token class; the template spells no colour.

**No as-of, and none threaded.** Status, assignee, percent and estimate are current-state
columns with no time dimension, so nothing here is dated — as in ``web.search`` — and
byte-identical regeneration is unconditional: a pure function of stored rows, no clock
read. Routed at ``/board`` because the bare ``/projects/{id}`` is the JSON read, registered
first and always winning the match — ``gantt.py`` sidesteps it the same way.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.models import TASK_STATUSES, Project, Task, TaskDependency, Workstream
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES


def columns(tasks: Sequence[Task], waits_for: dict[int, int] | None = None) -> list[dict[str, Any]]:
    """One column per status in the model's vocabulary, each with its own count.

    ``waits_for`` is each task id's dependency count — 0 for a task no ``dict``
    names, exactly the count :func:`_waits_for` returns and never a lazy load
    off ``task.dependencies_as_successor`` per card.
    """
    counts = waits_for or {}
    filed: dict[str, list[dict[str, Any]]] = {status: [] for status in TASK_STATUSES}
    for task in tasks:
        filed[task.status].append({"task": task, "waits_for": counts.get(task.id, 0)})
    return [{"status": s, "tasks": t, "count": len(t)} for s, t in filed.items()]


def _waits_for(db: Session, task_ids: Sequence[int]) -> dict[int, int]:
    """Every task's dependency count in ONE query — never one per card."""
    if not task_ids:
        return {}
    rows = db.execute(
        select(TaskDependency.successor_task_id, func.count())
        .where(TaskDependency.successor_task_id.in_(task_ids))
        .group_by(TaskDependency.successor_task_id)
    )  # a Result also carries .keys(), so dict() on it directly reads as a mapping
    return {task_id: count for task_id, count in rows}


def create_board_router() -> APIRouter:
    """``GET /projects/{id}/board``: no as-of — see the module docstring."""
    router = APIRouter(route_class=PageRoute)

    @router.get("/projects/{project_id}/board", response_class=HTMLResponse)
    def board(request: Request, project_id: int, db: Db) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        # ONE query for the whole board: the join scopes it to this project and each task's
        # workstream and assignee ride in on the same round trip, never a lazy load per card.
        # Ordered by workstream then task, so a column reads grouped and a refetch is stable.
        tasks = db.scalars(
            select(Task)
            .join(Workstream)
            .where(Workstream.project_id == project.id)
            .order_by(Workstream.name, Workstream.id, Task.name, Task.id)
            .options(joinedload(Task.workstream), joinedload(Task.assignee))
        ).all()
        waits_for = _waits_for(db, [task.id for task in tasks])
        context = {
            "project": project,
            "columns": columns(tasks, waits_for),
            "total": len(tasks),
        }
        return TEMPLATES.TemplateResponse(request, "board.html", context)

    return router
