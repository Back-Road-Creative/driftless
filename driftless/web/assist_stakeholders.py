"""``GET /projects/{id}/assist/stakeholders`` — the stakeholder engagement and
communications assistant, the first CALCULATOR-mode assistant page: the
power/interest grid, the current-versus-desired engagement matrix with gap
actions (a ``?desired=<id>:<level>`` what-if input, GET only — never a write),
and the communications matrix. Every figure comes straight from
``driftless.calc.stakeholders``, adapted from this project's own
``Stakeholder`` rows; nothing here recomputes what that module already owns.

Mounted the same way ``project_hub`` is: a per-project page keyed to a
``default_as_of`` (a fixed date for a pinned test render, ``date.today`` for the
served app), with ``PageRoute`` for the designed HTML error pages. ``Stakeholder``
carries no date of its own, so ``as_of`` is threaded only for the header every
sibling project page prints, never to filter a row.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.calc.stakeholders import (
    ENGAGEMENT_LEVELS,
    StakeholderRow,
    communications_matrix,
    engagement_gap,
    inferred_current_engagement,
    power_interest_grid,
)
from driftless.models import Project, Stakeholder
from driftless.pmbok.definitions import TECHNIQUES
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

#: The techniques this page runs, cited on its provenance block.
GRID_TECHNIQUE = "stakeholder_analysis"
MATRIX_TECHNIQUE = "stakeholder_engagement_assessment_matrix"
METHODS_TECHNIQUE = "communication_methods"


def _parse_desired(raw: str | None, stakeholders: Sequence[Stakeholder]) -> tuple[int, str] | None:
    """The one ``?desired=<id>:<level>`` override, or ``None`` when absent.

    Refuses (422, the page-surface's own "your input does not parse" shell) rather
    than silently ignoring a malformed or out-of-project id: a what-if that quietly
    did nothing would look identical to one that had not been tried yet.
    """
    if raw is None:
        return None
    sid_text, sep, level = raw.partition(":")
    if not sep or not sid_text.isdigit():
        raise HTTPException(422, f"desired must be '<id>:<level>', got {raw!r}")
    if level not in ENGAGEMENT_LEVELS:
        raise HTTPException(422, f"unknown engagement level: {level!r}")
    sid = int(sid_text)
    if sid not in {s.id for s in stakeholders}:
        raise HTTPException(422, f"stakeholder {sid} is not on this project")
    return sid, level


def create_assist_stakeholders_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The stakeholder assist page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/assist/stakeholders", response_class=HTMLResponse)
    def assist_stakeholders(
        request: Request,
        project_id: int,
        db: Db,
        at: date = Depends(resolve_as_of),
        desired: str | None = None,
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        stakeholders = list(
            db.scalars(
                select(Stakeholder)
                .where(Stakeholder.project_id == project.id)
                .order_by(Stakeholder.id)
            )
        )
        override = _parse_desired(desired, stakeholders)
        rows = [
            StakeholderRow(s.name, s.interest, s.influence, s.comms_cadence) for s in stakeholders
        ]
        engagement_rows = []
        for stakeholder in stakeholders:
            current = inferred_current_engagement(stakeholder.interest)
            wanted = override[1] if override and override[0] == stakeholder.id else current
            engagement_rows.append(
                {
                    "stakeholder": stakeholder,
                    "current": current,
                    "desired": wanted,
                    "gap": engagement_gap(current, wanted),
                }
            )
        context: dict[str, Any] = {
            "project": project,
            "as_of": at.isoformat(),
            "grid": power_interest_grid(rows),
            "engagement_rows": engagement_rows,
            "engagement_levels": ENGAGEMENT_LEVELS,
            "matrix": communications_matrix(rows),
            "provenance": {
                "grid": TECHNIQUES[GRID_TECHNIQUE],
                "matrix": TECHNIQUES[MATRIX_TECHNIQUE],
                "methods": TECHNIQUES[METHODS_TECHNIQUE],
            },
        }
        return TEMPLATES.TemplateResponse(request, "assist_stakeholders.html", context)

    return router
