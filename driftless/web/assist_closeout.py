"""Project closeout: ``GET /projects/{project_id}/assist/closeout``.

Close Project or Phase (4.7) reads accepted deliverables, a business case and a
final report and produces a final report, the final product/service result, and
the lessons learned register. This page shows the three things the store can
actually answer without a second closeout artifact of its own: deliverable
acceptance (read straight off ``Milestone`` status — the sign-off ledger a
milestone's ``status`` already is), the project's lessons (``LessonLearned``
rows), and a final-report summary built from the same figures the existing
report engine renders, never a second computation of them.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.assess import adapters
from driftless.models import LessonLearned, Milestone, Project
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

#: The PMBOK-6 process this page serves — Close Project or Phase.
PROCESS_ID = "4.7"


def _milestones(db: Db, project: Project, at: date) -> list[Milestone]:
    rows = db.scalars(
        select(Milestone)
        .where(Milestone.project_id == project.id)
        .where(Milestone.target_date <= at)
        .order_by(Milestone.id)
    ).all()
    return list(rows)


def _lessons(db: Db, project: Project, at: date) -> list[LessonLearned]:
    rows = db.scalars(
        select(LessonLearned)
        .where(LessonLearned.project_id == project.id)
        .where(LessonLearned.raised_on <= at)
        .order_by(LessonLearned.id)
    ).all()
    return list(rows)


def create_assist_closeout_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The closeout page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/assist/closeout", response_class=HTMLResponse)
    def assist_closeout(
        request: Request, project_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        milestones = _milestones(db, project, at)
        met = [m for m in milestones if m.status == "met"]
        snap = adapters.project_snapshot(db, project, at)
        context = {
            "project": project,
            "as_of": at.isoformat(),
            "milestones": milestones,
            "milestones_met": len(met),
            "milestones_total": len(milestones),
            "all_milestones_met": bool(milestones) and len(met) == len(milestones),
            "lessons": _lessons(db, project, at),
            "final_report": {
                "bac": round(snap.bac, 2),
                "eac": None if snap.eac is None else round(snap.eac, 2),
                "vac": None if snap.vac is None else round(snap.vac, 2),
            },
            "process": PROCESS_ID,
        }
        return TEMPLATES.TemplateResponse(request, "assist_closeout.html", context)

    return router
