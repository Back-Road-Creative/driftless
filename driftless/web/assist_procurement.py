"""The procurement decision calculators: ``GET /projects/{project_id}/assist/procurement``.

Serves the techniques Plan Procurement Management (12.1) and Conduct Procurements
(12.2) name that ``assess.model.ASSISTANT_ROUTES`` now routes: ``make_or_buy_analysis``,
``proposal_evaluation`` and ``source_selection_analysis``. Everything on the page is a
no-write what-if over ``driftless.calc.procurement`` plus this project's signed
``ProcurementAgreement`` rows, read straight off the store — nothing here writes an
agreement or a lesson. The closure checklist is derived from those same rows' own
``status`` column, never a second tracked field: Control Procurements (12.3) closes an
agreement by setting its status, so counting statuses IS reading closure progress.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.calc import procurement as calc
from driftless.models import Project, ProcurementAgreement
from driftless.pmbok.definitions import TECHNIQUES
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

#: The PMBOK-6 processes this page serves — cited in provenance, not derived, the
#: same way ``assist_evm``'s ``PROCESS_ID`` is a literal nothing else needs.
PROCESS_IDS = ("12.1", "12.2", "12.3")


def _agreements(db: Db, project: Project, at: date) -> list[ProcurementAgreement]:
    rows = db.scalars(
        select(ProcurementAgreement)
        .where(ProcurementAgreement.project_id == project.id)
        .where(ProcurementAgreement.start_date <= at)
        .order_by(ProcurementAgreement.id)
    ).all()
    return list(rows)


def _closure_checklist(agreements: list[ProcurementAgreement]) -> dict[str, object]:
    """Closure progress read straight off ``status`` — no second tracked field."""
    closed = [a for a in agreements if a.status == "closed"]
    disputed = [a for a in agreements if a.status == "disputed"]
    return {
        "total": len(agreements),
        "closed": len(closed),
        "disputed": [a.vendor for a in disputed],
        "all_closed": bool(agreements) and len(closed) == len(agreements),
    }


def _provenance(as_of: date) -> dict[str, str]:
    technique = TECHNIQUES["make_or_buy_analysis"]
    return {
        "technique": technique.display_name,
        "processes": ", ".join(PROCESS_IDS),
        "as_of": as_of.isoformat(),
        "source": technique.source_version or technique.source,
    }


def create_assist_procurement_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The procurement calculator page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/assist/procurement", response_class=HTMLResponse)
    def assist_procurement(
        request: Request,
        project_id: int,
        db: Db,
        at: date = Depends(resolve_as_of),
        make_cost: float | None = None,
        buy_cost: float | None = None,
        volume: float | None = None,
        fixed_make_cost: float | None = None,
        bidder_a_name: str | None = None,
        bidder_a_price: float | None = None,
        bidder_a_quality: float | None = None,
        bidder_b_name: str | None = None,
        bidder_b_price: float | None = None,
        bidder_b_quality: float | None = None,
        weight_price: float | None = None,
        weight_quality: float | None = None,
        scope_certainty: calc.ScopeCertainty | None = None,
        risk_appetite: calc.RiskAppetite | None = None,
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        agreements = _agreements(db, project, at)

        make_or_buy_result = None
        if None not in (make_cost, buy_cost, volume, fixed_make_cost):
            assert make_cost is not None and buy_cost is not None
            assert volume is not None and fixed_make_cost is not None
            make_or_buy_result = calc.make_or_buy(make_cost, buy_cost, volume, fixed_make_cost)

        bid_result = None
        if None not in (
            bidder_a_name,
            bidder_a_price,
            bidder_a_quality,
            bidder_b_name,
            bidder_b_price,
            bidder_b_quality,
            weight_price,
            weight_quality,
        ):
            assert bidder_a_name is not None and bidder_b_name is not None
            assert bidder_a_price is not None and bidder_a_quality is not None
            assert bidder_b_price is not None and bidder_b_quality is not None
            assert weight_price is not None and weight_quality is not None
            bid_result = calc.bid_score(
                proposals={
                    bidder_a_name: {"price": bidder_a_price, "quality": bidder_a_quality},
                    bidder_b_name: {"price": bidder_b_price, "quality": bidder_b_quality},
                },
                criteria_weights={"price": weight_price, "quality": weight_quality},
            )

        contract_result = None
        if scope_certainty is not None and risk_appetite is not None:
            contract_result = calc.contract_type_guidance(scope_certainty, risk_appetite)

        context = {
            "project": project,
            "as_of": at.isoformat(),
            "agreements": agreements,
            "checklist": _closure_checklist(agreements),
            "make_or_buy": {
                "make_cost": make_cost,
                "buy_cost": buy_cost,
                "volume": volume,
                "fixed_make_cost": fixed_make_cost,
                "result": make_or_buy_result,
            },
            "bid": {
                "bidder_a_name": bidder_a_name,
                "bidder_a_price": bidder_a_price,
                "bidder_a_quality": bidder_a_quality,
                "bidder_b_name": bidder_b_name,
                "bidder_b_price": bidder_b_price,
                "bidder_b_quality": bidder_b_quality,
                "weight_price": weight_price,
                "weight_quality": weight_quality,
                "result": bid_result,
            },
            "contract": {
                "scope_certainty": scope_certainty,
                "risk_appetite": risk_appetite,
                "result": contract_result,
            },
            "provenance": _provenance(at),
        }
        return TEMPLATES.TemplateResponse(request, "assist_procurement.html", context)

    return router
