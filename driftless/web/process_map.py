"""One project's PMBOK process map: ``GET /projects/{project_id}/process-map``.

Third slice carved out of ``web/pages.py``. It reads and renders only: the whole page is
computed inside a single ``state.prefetched`` scope, so ``project_process_states`` runs
once and is threaded into the grid, the per-area rings and the sign-off picker instead of
each re-walking the store.

The picker's rows come through the same ``state_word`` the grid cells do, so it cannot
call a process something the cell above it does not, and each row's ``ref`` is built by
``state.process_subject_ref`` — the one home for that convention — so a decision always
names the process the cell showed and the template never assembles a subject by hand.

Posting that decision lives in ``web/sign_off.py`` (``POST /sign-off``), which redirects a
process sign-off back to this path. The two sides share a path literal built from a
validated id, not an import.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.models import Project
from driftless.pmbok import catalog, state, tailoring
from driftless.pmbok.model import KnowledgeArea, ProcessGroup
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES
from driftless.web.views import LEGEND, area_completeness, pct, process_grid, state_word


def create_process_map_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The per-project process map, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/process-map", response_class=HTMLResponse)
    def process_map(
        request: Request, project_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        # One prefetch scope for the whole render: project_process_states is
        # computed ONCE and threaded into process_grid/area_completeness below
        # instead of each re-walking the store; state.completeness's own walk
        # still rides the same cache (see pmbok.state.prefetched).
        with state.prefetched(db, [project]):
            states = state.project_process_states(project, db, at)
            grid = process_grid(states)
            rings = area_completeness(states)
            completeness = pct(state.completeness(project, db, at))
        context = {
            "project": project,
            "as_of": at.isoformat(),
            "groups": [g.value for g in ProcessGroup],
            "areas": [a.value for a in KnowledgeArea],
            "grid": grid,
            "legend": LEGEND,
            "completeness": completeness,
            # Raw per-area fractions drive the ring geometry; the pre-formatted
            # labels reuse pct so a ring's text can never drift from the header.
            "rings": rings,
            "ring_labels": {area: pct(frac) for area, frac in rings.items()},
            "count": len(states),
            # The sign-off picker's rows, in catalog order and carrying the state the
            # grid drew — through the SAME ``state_word``, so the picker cannot call a
            # process something the cell above it does not. ``ref`` is built HERE by
            # state.process_subject_ref — the one home for that convention — so a
            # decision always names the process the cell showed, and the template never
            # assembles a subject by hand.
            "processes": [
                {
                    "id": process.id,
                    "name": process.name,
                    "state": state_word(process, process_state),
                    "ref": state.process_subject_ref(process, project),
                }
                for process, process_state in states
            ],
            # This project's hybrid tailoring: every Monitoring & Controlling
            # process, in catalog order, paired with the mode its delivery_mode
            # profile reads it on and the one-sentence reason
            # (driftless.pmbok.tailoring — the totality tests live there).
            "tailoring_profile": tailoring.profile_for(project.delivery_mode).display_name,
            "tailoring": [
                {
                    "id": process.id,
                    "name": process.name,
                    "mode_word": tailoring.mode_word(control.mode),
                    "reason": control.reason,
                }
                for process in catalog.by_group(ProcessGroup.MONITORING)
                for control in [tailoring.control_tailoring(process.id, project.delivery_mode)]
                if control is not None
            ],
        }
        return TEMPLATES.TemplateResponse(request, "process_map.html", context)

    return router
