"""The weekly-status edit flow: the RAG snapshot form, and the post that files it.

One controller because it is one loop — the GET renders the trend and cost curve the POST
extends, and the POST redirects back to the GET at the as-of it just filed. The write goes
through the validated boundary the API and the wizard use, never a bespoke web-only path,
so the single-write-path guarantee holds from the browser too. The page degrades without
JavaScript; ``static/driftless.js`` only makes the swap feel instant.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.deps import get_session, resolved_actor
from driftless.api.records import fetch
from driftless.assess import adapters
from driftless.assess.percent import stamped_percent
from driftless.calc.evidence_age import evidence_age
from driftless.services.status_snapshots import create_status_snapshot
from driftless.models import Project, RAG_STATUSES, StatusSnapshot
from driftless.web import csrf
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.receipt import attach_receipt
from driftless.web.templating import TEMPLATES
from driftless.web.views import evm_curve, trend_series

Db = Annotated[Session, Depends(get_session)]


def create_status_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The weekly-status form and its submit, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/status", response_class=HTMLResponse)
    def status_form(
        request: Request, project_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        # The append-only StatusSnapshot series IS the trend. Ordered by ``id`` --
        # RECORDING order, not ``taken_on`` -- because a same-date correction (see
        # ``models.records.StatusSnapshot``) means two rows can now share a date,
        # and ``trend_series`` needs recording order to pick the one that wins.
        snapshots = db.scalars(
            select(StatusSnapshot)
            .where(StatusSnapshot.project_id == project.id)
            .order_by(StatusSnapshot.id)
        ).all()
        series = trend_series(snapshots)
        # Planned-vs-actual cost S-curve. Costs load once; the baseline hierarchy
        # is eager-loaded so the in-memory sweep in ``evm_curve`` never fires a
        # query per sample date (``snapshot_from`` is pure once baselines are in).
        project = db.scalars(
            select(Project).where(Project.id == project.id).options(*adapters.eager_project())
        ).one()
        costs = adapters.project_costs(db, project)
        # The evidence behind THIS page's RAG and EVM figures: every status
        # snapshot's own reading date, plus every cost entry's — the two record
        # kinds the percent-complete stamp and the cost curve are built from.
        evidence = evidence_age(
            at, [snap.taken_on for snap in snapshots] + [c.incurred_on for c in costs]
        )
        context = {
            "project": project,
            "as_of": at.isoformat(),
            "percent": stamped_percent(db, project, at),
            "rags": list(RAG_STATUSES),
            "series": series,
            "evm": evm_curve(project, costs, at),
            "evidence": evidence,
        }
        response = TEMPLATES.TemplateResponse(request, "status_form.html", context)
        return attach_receipt(response, at)

    @router.get("/projects/{project_id}/status/inputs", response_class=HTMLResponse)
    def status_inputs(
        request: Request, project_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        """The read-only provenance page behind the trend: every StatusSnapshot row
        for this project, in the same recording order ``trend_series`` consumes them
        in -- unfiltered by ``at``, because the trend itself is (see ``status_form``:
        the query it reads from carries no ``taken_on`` bound). Linked from the
        percent/RAG figure on ``status_form.html`` so the reading is one click from
        the rows it came from, never a number to take on faith."""
        project = fetch(db, Project, project_id)
        snapshots = db.scalars(
            select(StatusSnapshot)
            .where(StatusSnapshot.project_id == project.id)
            .order_by(StatusSnapshot.id)
        ).all()
        context = {
            "project": project,
            "as_of": at.isoformat(),
            "snapshots": snapshots,
        }
        response = TEMPLATES.TemplateResponse(request, "status_inputs.html", context)
        return attach_receipt(response, at)

    @router.post("/projects/{project_id}/status")
    def status_submit(
        request: Request,
        project_id: int,
        db: Db,
        rag_status: Annotated[str, Form()] = "green",
        note: Annotated[str | None, Form()] = None,
        as_of: Annotated[date | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """File the weekly snapshot through the SAME validated boundary the JSON
        route uses: ``StatusSnapshotIn`` refuses a bad RAG or oversize note as 422
        at the schema — never handed to the ORM to bounce off a CHECK as a 409 or
        slip past a VARCHAR SQLite does not enforce — and ``create_status_snapshot``
        stamps the percent from calc, never typed. The two write paths are one."""
        csrf.require(request, csrf_token)  # before any read or write
        project = fetch(db, Project, project_id)
        at = resolve_as_of(as_of)
        try:
            payload = s.StatusSnapshotIn(
                project_id=project.id,
                taken_on=at,
                rag_status=rag_status,  # type: ignore[arg-type]
                note=note or None,
            )
        except ValidationError as error:
            raise HTTPException(422, str(error)) from error
        create_status_snapshot(db, payload, resolved_actor(request))
        return RedirectResponse(
            f"/projects/{project_id}/status?as_of={at.isoformat()}", status_code=303
        )

    return router
