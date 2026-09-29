"""One project's RAID log: ``GET /projects/{project_id}/raid``.

Fourth slice carved out of ``web/pages.py``. Risks, issues and change requests for one
project, each ordered by id so a refetch is byte-identical, and each read with its own
statement rather than through a relationship walk.

Read-only, and it shares nothing with the write path it left behind: no CSRF pair rule,
no sign-off redirect, no wizard context.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.models import ChangeRequest, Issue, Project, Risk
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

# High-exposure threshold for an open risk's severity badge: the same 1000 the
# template used to hardcode, moved here because deciding which badge class a
# row wears is the router's job, not the template's.
_HIGH_EXPOSURE = 1000


def _risk_severity(risk: Risk) -> str:
    """The badge class token for one risk row -- open-and-costly reads red,
    open reads amber, anything closed/mitigated/realised reads green. The
    template renders this token verbatim; it decides nothing."""
    if risk.status != "open":
        return "sev-green"
    return "sev-red" if risk.exposure >= _HIGH_EXPOSURE else "sev-amber"


def _risk_row(risk: Risk) -> dict[str, Any]:
    """One risk, as the template's row shape: every field it already reads,
    plus the ``severity`` token computed above."""
    return {
        "description": risk.description,
        "probability": risk.probability,
        "impact": risk.impact,
        "exposure": risk.exposure,
        "response": risk.response,
        "owner": risk.owner,
        "status": risk.status,
        "severity": _risk_severity(risk),
    }


def create_raid_log_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The per-project RAID log, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/raid", response_class=HTMLResponse)
    def project_raid(
        request: Request, project_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        risks = db.scalars(
            select(Risk).where(Risk.project_id == project.id).order_by(Risk.id)
        ).all()
        issues = db.scalars(
            select(Issue).where(Issue.project_id == project.id).order_by(Issue.id)
        ).all()
        changes = db.scalars(
            select(ChangeRequest)
            .where(ChangeRequest.project_id == project.id)
            .order_by(ChangeRequest.id)
        ).all()
        context = {
            "project": project,
            "as_of": at.isoformat(),
            "risks": [_risk_row(r) for r in risks],
            "issues": issues,
            "changes": changes,
        }
        return TEMPLATES.TemplateResponse(request, "raid.html", context)

    return router
