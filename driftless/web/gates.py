"""One project's stage gates: ``GET /projects/{project_id}/gates``.

A gate (plan gap G20) is a thin ``Gate`` row — name, sequence position, and the
PMBOK processes required to pass — with no status column of its own. Readiness is
computed here on every render, exactly the way ``web/process_map.py`` computes
process state: :func:`driftless.pmbok.state.gate_readiness` walks the same
derived process states the map draws, so a gate can never disagree with the map
about whether a process it names is done. Passage is read off the sign-off
ledger the same way (:func:`driftless.pmbok.state.gate_passed`).

Posting a decision lives in ``web/sign_off.py`` (``POST /sign-off``), which
redirects a gate sign-off back to this path — the same shape the process map and
the baseline diff page already use.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.models import Gate, Project, SignOff
from driftless.pmbok import state
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES


def _signoffs(db: Session, gate: Gate) -> list[SignOff]:
    """One gate's own sign-off ledger, newest first."""
    return list(
        db.scalars(
            select(SignOff)
            .where(
                SignOff.subject_kind == "gate", SignOff.subject_ref == state.gate_subject_ref(gate)
            )
            .order_by(SignOff.signed_at.desc())
        )
    )


def create_gates_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The per-project gate list, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/gates", response_class=HTMLResponse)
    def gates(
        request: Request, project_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        rows = db.scalars(
            select(Gate).where(Gate.project_id == project_id).order_by(Gate.position, Gate.id)
        ).all()
        gate_rows: list[dict[str, object]] = []
        with state.prefetched(db, [project]):
            for gate in rows:
                ready, missing = state.gate_readiness(gate, project, db, at)
                gate_rows.append(
                    {
                        "gate": gate,
                        "ready": ready,
                        "missing": missing,
                        "passed": state.gate_passed(gate, db, at),
                        "signoffs": _signoffs(db, gate),
                    }
                )
        context = {"project": project, "as_of": at.isoformat(), "gates": gate_rows}
        return TEMPLATES.TemplateResponse(request, "gates.html", context)

    return router
