"""Portfolio and program drill pages: one node's rollup KPIs plus its children's
rows, sliced from the SAME ``gather.overview`` tree home renders, so a drill
figure can never disagree with the dashboard. ``gather.find_node`` locates the
node by the REAL DB id ``gather.table_rows`` stamped on the home link (via
``gather.id_tree``); only a genuinely absent id 404s, like ``api.app``'s ``fetch``.

Routed at ``/portfolios/{id}/rollup``, not the bare ``/portfolios/{id}`` — that
path is already the JSON REST read (``api/crud.py``'s ``reads``), registered on
``app`` first, so it would always win. Every per-project page sidesteps the
identical ``/projects/{id}`` collision the same way, with a segment after the id;
``tests/test_web_routes_not_shadowed.py`` walks the real app and asserts it for all
of them rather than leaving it to each module to remember."""

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from driftless.api.deps import get_session
from driftless.calc.rollup import on_track_share
from driftless.report import gather
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.scorecard_rollup import scorecard_rollup
from driftless.web.templating import TEMPLATES

Db = Annotated[Session, Depends(get_session)]


def _render(request: Request, db: Session, as_of: date, kind: str, node_id: int) -> HTMLResponse:
    total = gather.overview(db, as_of)
    found = gather.find_node(total.children, gather.id_tree(db), kind, node_id)
    if found is None:
        raise HTTPException(404, f"{kind} {node_id} not found")
    node, ids = found
    share = on_track_share(gather.leaves(node))
    scorecard_rows = scorecard_rollup(db, as_of, kind, ids)
    context = {
        "as_of": as_of.isoformat(),
        "kind": kind,
        "total": gather.cell(node),
        "flow": gather.flow_cell(node),
        "on_track": f"{share:.0f}%" if share is not None else "no data yet",
        "rows": gather.table_rows(node.children, ids.children),
        "scorecard_rows": scorecard_rows,
    }
    return TEMPLATES.TemplateResponse(request, "drill.html", context)


def create_drills_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """``GET /portfolios/{id}/rollup`` and ``GET /programs/{id}/rollup``,
    defaulting to the same resolved-per-request as-of the other routers use."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/portfolios/{portfolio_id}/rollup", response_class=HTMLResponse)
    def portfolio_drill(
        request: Request, portfolio_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        return _render(request, db, at, "portfolio", portfolio_id)

    @router.get("/programs/{program_id}/rollup", response_class=HTMLResponse)
    def program_drill(
        request: Request, program_id: int, db: Db, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        return _render(request, db, at, "program", program_id)

    return router
