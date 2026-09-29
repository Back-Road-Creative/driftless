"""The risk-response planner: ``GET``/``POST /projects/{project_id}/assist/risk-responses``.

Routes four of the risk knowledge area's routed techniques
(``assess.model.ASSISTANT_ROUTES``): ``strategies_for_threats``,
``strategies_for_opportunities``, ``contingent_response_strategies`` and
``strategies_for_overall_project_risk``. The register half is a read — every figure
comes from ``driftless.pmbok.risk_facts.gather``, the one adapter the threat board,
the gantt note and the cost workbench line also read, so this page can never
disagree with any of them. The what-if half recomputes a hypothetical residual
score purely in this response, from posted probability/impact, and writes nothing.
The one write this page allows is filing a response, through
``driftless.services.risk_writes.file_risk_response`` — the same validated boundary
the JSON ``POST /risk-responses`` route uses, so the two write paths are one.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.assess import adapters
from driftless.assess.exposure import contingency_held
from driftless.models import Person, Project, Risk, RiskResponse
from driftless.models.records import OPEN_RISK_STATUSES
from driftless.models.risk import OPPORTUNITY_STRATEGIES, THREAT_STRATEGIES
from driftless.pmbok import risk_facts
from driftless.pmbok.definitions import TECHNIQUES
from driftless.services.risk_writes import file_risk_response
from driftless.web import csrf
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

PROCESS_ID = "11.5"  # Plan Risk Responses — every routed technique below is one of its tools.


def _strategies_for(kind: str) -> tuple[str, ...]:
    allowed = THREAT_STRATEGIES if kind == "threat" else OPPORTUNITY_STRATEGIES
    return tuple(sorted(allowed))


def _register(session: Session, project: Project, at: date) -> list[dict[str, Any]]:
    """Every open risk, its latest response filed as of ``at`` (if any) and its residual read."""
    risks = session.scalars(
        select(Risk)
        .where(Risk.project_id == project.id, Risk.status.in_(OPEN_RISK_STATUSES))
        .order_by(Risk.exposure.desc(), Risk.id)
    ).all()
    latest = risk_facts.latest_by_risk(  # the one place "most recent response" is decided
        list(session.scalars(select(RiskResponse).where(RiskResponse.project_id == project.id))),
        at,
    )
    rows = []
    for risk in risks:
        response = latest.get(risk.id)
        rows.append(
            {
                "risk": risk,
                "exposure": round(risk.exposure, 2),
                "response": response,
                "residual_exposure": (
                    round(response.residual_exposure, 2)
                    if response is not None
                    else round(risk.exposure, 2)
                ),
                "no_response_planned": response is None,
            }
        )
    return rows


def create_assist_risk_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The risk-response planner page and its one write, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    def _context(
        request: Request, project: Project, db: Session, at: date, risk_id: int | None
    ) -> dict[str, Any]:
        register = _register(db, project, at)
        open_risk_ids = [row["risk"].id for row in register]
        target_id = risk_id if risk_id in open_risk_ids else next(iter(open_risk_ids), None)
        target = next((row["risk"] for row in register if row["risk"].id == target_id), None)
        owners = db.scalars(select(Person).order_by(Person.name)).all()
        facts = risk_facts.gather(db, project, at)
        held = contingency_held(
            db, project, adapters.remaining_budget(adapters.project_snapshot(db, project, at))
        )
        over_contingency = [
            row
            for row in register
            if row["response"] is not None and row["response"].cost_of_response > held
        ]
        return {
            "project": project,
            "as_of": at.isoformat(),
            "register": register,
            "target": target,
            "strategies": _strategies_for(target.kind) if target is not None else (),
            "owners": owners,
            "facts": facts,
            "over_contingency": over_contingency,
            "provenance": {
                "technique": TECHNIQUES["strategies_for_threats"].display_name,
                "process": PROCESS_ID,
                "as_of": at.isoformat(),
            },
        }

    @router.get("/projects/{project_id}/assist/risk-responses", response_class=HTMLResponse)
    def assist_risk_responses(
        request: Request,
        project_id: int,
        db: Db,
        at: date = Depends(resolve_as_of),
        risk_id: int | None = None,
        whatif_probability: float | None = None,
        whatif_impact: float | None = None,
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        context = _context(request, project, db, at, risk_id)
        whatif = None
        if whatif_probability is not None and whatif_impact is not None:
            whatif = {
                "probability": round(whatif_probability, 3),
                "impact": round(whatif_impact, 2),
                "residual_exposure": round(whatif_probability * whatif_impact, 2),
            }
        context["whatif"] = whatif
        return TEMPLATES.TemplateResponse(request, "assist_risk.html", context)

    @router.post("/projects/{project_id}/assist/risk-responses")
    def file_response(
        request: Request,
        project_id: int,
        db: Db,
        risk_id: Annotated[int, Form()],
        strategy: Annotated[str, Form()],
        owner_id: Annotated[int, Form()],
        trigger: Annotated[str, Form()],
        planned_action: Annotated[str, Form()],
        residual_probability: Annotated[float, Form()],
        residual_impact: Annotated[float, Form()],
        cost_of_response: Annotated[float, Form()] = 0.0,
        schedule_days: Annotated[int, Form()] = 0,
        status: Annotated[str, Form()] = "planned",
        actor: Annotated[str, Form()] = "web",
        as_of: Annotated[date | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """File one response plan through the same boundary the JSON route uses."""
        csrf.require(request, csrf_token)  # before any read or write
        project = fetch(db, Project, project_id)
        at = resolve_as_of(as_of)
        try:
            payload = s.RiskResponseIn(
                project_id=project.id,
                risk_id=risk_id,
                strategy=strategy,  # type: ignore[arg-type]
                owner_id=owner_id,
                trigger=trigger,
                planned_action=planned_action,
                residual_probability=residual_probability,
                residual_impact=residual_impact,
                cost_of_response=cost_of_response,
                schedule_days=schedule_days,
                status=status,  # type: ignore[arg-type]
                actor=actor or "web",
                as_of=at,
            )
        except ValidationError as error:
            raise HTTPException(422, str(error)) from error
        file_risk_response(db, payload)
        return RedirectResponse(
            f"/projects/{project_id}/assist/risk-responses?as_of={at.isoformat()}",
            status_code=303,
        )

    return router
