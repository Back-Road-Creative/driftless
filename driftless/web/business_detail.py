"""One business and what hangs off it: ``GET /business/{business_id}``.

Fifth slice carved out of ``web/pages.py``. Read-only: the business, its
portfolio → program → project hierarchy shaped for the template, and the
business-wide process completeness that ``pmbok.rollup`` computes from the same cells
the business MAP draws.

Completeness is formatted here rather than in the template because "no cells yet" is a
different answer from "0%": ``business_completeness`` returns ``None`` for the first,
which becomes ``no data yet`` — a percentage would claim a measurement nobody made.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.models import Business
from driftless.pmbok.rollup import business_completeness, business_process_cells
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES


def create_business_detail_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The business detail page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/business/{business_id}", response_class=HTMLResponse)
    def business_detail(
        request: Request, business_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        business = fetch(db, Business, business_id)
        cells = business_process_cells(db, at)
        comp = business_completeness(cells)
        comp_val = f"{comp:.0%}" if comp is not None else "no data yet"
        portfolios = [
            {
                "id": p.id,
                "name": p.name,
                "programs": [
                    {
                        "id": prg.id,
                        "name": prg.name,
                        "projects": [{"id": prj.id, "name": prj.name} for prj in prg.projects],
                    }
                    for prg in p.programs
                ],
            }
            for p in business.portfolios
        ]
        context = {
            "business": business,
            "as_of": at.isoformat(),
            "completeness": comp_val,
            "portfolios": portfolios,
        }
        return TEMPLATES.TemplateResponse(request, "business_detail.html", context)

    return router
