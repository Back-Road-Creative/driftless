"""One page per project: ``/projects/{project_id}/hub`` — the project hub.

Composes a project's health at a glance from the SAME engines the sibling pages
render from — gather's EVM adapter (via ``pages.evm_curve``), pages' threat
cards scoped to this project (``pages.threat_cards(db, at, project_id=...)`` —
this project's assessment only, never the whole store's), and per-area
completeness — plus scoped RAID counts and milestones, with the three deep pages
(process map, wizard, weekly status) linked as its sections. Adapts and renders
only — no figure the engines own is recomputed — and reads no wall clock, so a
pinned as-of regenerates byte-identically. The bare ``/projects/{id}`` path
belongs to the JSON API's project read (registered first, so it always wins the
match); ``/hub`` keeps the API contract intact while giving the browser page its
own address.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from driftless.api.app import Db, fetch
from driftless.assess import adapters
from driftless.assess.evaluators.schedule import milestone_slipped
from driftless.models import ChangeRequest, Issue, Milestone, Project, Risk
from driftless.pmbok import state
from driftless.report import gather
from driftless.web.pages import area_completeness, evm_curve, pct, threat_cards
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

# "Open" per RAID model — risks reuse gather's OPEN_RISKS definition:
OPEN_ISSUES = ("open", "in_progress")  # an issue is open until resolved/closed
OPEN_CHANGES = ("proposed",)  # a change request is open only while proposed


def _open_count(
    db: Session,
    model: type[Risk | Issue | ChangeRequest],
    project_id: int,
    statuses: tuple[str, ...],
) -> int:
    """One RAID model's open-row count, scoped to the project — a plain aggregate."""
    where = (model.project_id == project_id, model.status.in_(statuses))
    return int(db.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def create_project_hub_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The per-project hub page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve = default_as_of if callable(default_as_of) else lambda: default_as_of

    @router.get("/projects/{project_id}/hub", response_class=HTMLResponse)
    def project_hub(
        request: Request, project_id: int, db: Db, as_of: date | None = None
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        at = as_of or resolve()
        # Scoped, never store-wide: this is a ONE-project page, and gather's
        # batched full-table read would hand it every project's spend.
        costs = adapters.project_costs(db, project)
        # One prefetch scope: project_process_states is computed ONCE and threaded
        # into area_completeness, mirroring pages.process_map; state.completeness's
        # own walk rides the same cache (pmbok.state.prefetched).
        with state.prefetched(db, [project]):
            states = state.project_process_states(project, db, at)
            rings = area_completeness(states)
            completeness = pct(state.completeness(project, db, at))
        milestones = [
            {
                "name": m.name,
                "target": m.target_date.isoformat(),
                "status": m.status,
                "slipped": milestone_slipped(m, at),
            }
            for m in db.scalars(
                select(Milestone)
                .where(Milestone.project_id == project.id)
                .order_by(Milestone.target_date, Milestone.id)
            )
        ]
        context: dict[str, Any] = {
            "project": project,
            "as_of": at.isoformat(),
            "completeness": completeness,
            "ring_labels": {area: pct(frac) for area, frac in rings.items()},
            "evm": evm_curve(project, costs, at),
            "threats": threat_cards(db, at, project_id=project.id),
            "raid": {
                "risks": _open_count(db, Risk, project.id, gather.OPEN_RISKS),
                "issues": _open_count(db, Issue, project.id, OPEN_ISSUES),
                "changes": _open_count(db, ChangeRequest, project.id, OPEN_CHANGES),
            },
            "milestones": milestones,
        }
        return TEMPLATES.TemplateResponse(request, "project_hub.html", context)

    return router
