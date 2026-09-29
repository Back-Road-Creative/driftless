"""Schedule health checks: ``GET /projects/{id}/schedule-health`` (page), and the same
rows exported with ``?format=csv`` — the ``?format=csv`` convention the API list routes
already use (:mod:`driftless.api.export`), so the download is not a second page route.

Thresholds follow the commonly used DCMA 14-point assessment — named once, here,
as the source of the numbers below. Nothing on this page is reported as "DCMA
compliant" or "certified": each row is a ratio against a threshold, pass, fail,
or not assessable, per :mod:`driftless.calc.dcma`.

Inputs are built from the SAME stored rows ``web.gantt`` and ``pmbok.schedule_facts``
already read — the newest approved baseline visible at ``as_of``, adapted into
``calc.network`` by :func:`schedule_facts.schedule_facts` — so this page can never
disagree with the network the Gantt page draws for the same as-of. This schema
tracks no actual-finish, forecast-finish or baseline-finish date distinct from the
approved plan's own planned windows, so ``actual_finish``/``forecast_finish``/
``baseline_finish`` are always empty: inventing an offender from a hole in the
data (every due task reads as "missed" when nothing tracks whether it finished)
would be worse than saying so, so checks 9, 11 and 14 always render "not
assessable" here — exactly the shape check 5 already uses for the same reason.
Resources ARE tracked (``Task.assignee``), so check 10 runs for real.

One computation feeds both the page and the CSV — :func:`_report` — so the two
surfaces can never disagree with each other either.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.deps import Db
from driftless.api.export import csv_cell
from driftless.api.records import fetch
from driftless.calc.dcma import CheckResult, assess_full
from driftless.models import Person, Project, Task
from driftless.pmbok.schedule_facts import schedule_facts
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

# humanize() renders these as "Cpli" / "Bei"; the two acronyms it cannot know.
_TITLES = {"cpli": "CPLI", "bei": "BEI"}


@dataclass(frozen=True)
class CheckRow:
    """One check, ready for either surface: a display name, the raw numbers, a
    status string (never "compliant"/"certified"), and offending tasks named."""

    name: str
    numerator: int
    denominator: int
    ratio: float
    threshold: float
    status: str
    note: str
    offending: tuple[str, ...]


def _status(check: CheckResult) -> str:
    if not check.assessable:
        return "not assessable"
    return "pass" if check.passed else "fail"


def _rows(results: Sequence[CheckResult], task_names: Mapping[str, str]) -> list[CheckRow]:
    return [
        CheckRow(
            name=_TITLES.get(check.name, check.name.replace("_", " ").title()),
            numerator=check.numerator,
            denominator=check.denominator,
            ratio=check.ratio,
            threshold=check.threshold,
            status=_status(check),
            note=check.note,
            offending=tuple(task_names.get(aid, aid) for aid in check.offending_ids),
        )
        for check in results
    ]


def _resources(db: Session, task_ids: set[str]) -> dict[str, tuple[str, ...]]:
    """Assigned people, batched in one statement rather than one query per
    task — an activity absent here carries no resource assignment at all."""
    ids = [int(aid) for aid in task_ids]
    rows = db.execute(
        select(Task.id, Person.name)
        .join(Person, Task.assignee_id == Person.id)
        .where(Task.id.in_(ids))
    )
    out: dict[str, list[str]] = {}
    for task_id, name in rows:
        out.setdefault(str(task_id), []).append(name)
    return {aid: tuple(names) for aid, names in out.items()}


def _report(db: Session, project: Project, at: date) -> list[CheckRow] | None:
    """The fourteen checks for ``project`` as of ``at``, or ``None`` when there
    is no approved, lined baseline to assess yet."""
    facts = schedule_facts(db, project, at)
    if facts is None:
        return None
    resources = _resources(db, set(facts.task_names))
    results = assess_full(
        facts.network,
        actual_finish={},
        forecast_finish={},
        resources=resources,
        baseline_finish={},
        as_of=at,
    )
    return _rows(results, facts.task_names)


def _csv(project_id: int, rows: list[Any]) -> Response:
    """The page's rows as a download: one line per check, offenders ``; ``-joined."""
    columns = ("check", "numerator", "denominator", "ratio", "threshold", "status", "offending")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        cells = (
            row.name,
            row.numerator,
            row.denominator,
            row.ratio,
            row.threshold,
            row.status,
            "; ".join(row.offending),
        )
        writer.writerow([csv_cell(cell) for cell in cells])
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"content-disposition": f'attachment; filename="schedule-health-{project_id}.csv"'},
    )


def create_schedule_health_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/schedule-health", response_class=HTMLResponse)
    def schedule_health(
        request: Request,
        project_id: int,
        db: Db,
        at: date = Depends(resolve_as_of),
        format: Literal["html", "csv"] = "html",
    ) -> Response:
        project = fetch(db, Project, project_id)
        rows = _report(db, project, at)
        if format == "csv":
            return _csv(project_id, rows or [])
        context: dict[str, Any] = {"project": project, "as_of": at.isoformat(), "rows": rows}
        return TEMPLATES.TemplateResponse(request, "schedule_health.html", context)

    return router
