"""Portfolio and program drill pages: one node's rollup KPIs plus its children's
rows, sliced from the SAME ``gather.overview`` tree home renders, so a drill
figure can never disagree with the dashboard. ``gather.find_node`` locates the
node by the REAL DB id ``gather.table_rows`` stamped on the home link (via
``gather.id_tree``); only a genuinely absent id 404s, like ``api.app``'s ``fetch``.

Routed at ``/portfolios/{id}/rollup``, not the bare ``/portfolios/{id}`` — that
path is already the JSON REST read (``api/app.py``'s ``_reads``), registered on
``app`` first, so it would always win. ``pages.py`` sidesteps the identical
``/projects/{id}`` collision the same way, with a segment after the id."""

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from driftless.api.app import get_session
from driftless.calc.rollup import on_track_share
from driftless.report import gather
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

Db = Annotated[Session, Depends(get_session)]


def _render(request: Request, db: Session, as_of: date, kind: str, node_id: int) -> HTMLResponse:
    total = gather.overview(db, as_of)
    found = gather.find_node(total.children, gather.id_tree(db), kind, node_id)
    if found is None:
        raise HTTPException(404, f"{kind} {node_id} not found")
    node, ids = found
    share = on_track_share(gather.leaves(node))
    context = {
        "as_of": as_of.isoformat(),
        "kind": kind,
        "total": gather.cell(node),
        "on_track": f"{share:.0f}%" if share is not None else "n/a",
        "rows": gather.table_rows(node.children, ids.children),
    }
    return TEMPLATES.TemplateResponse(request, "drill.html", context)


def create_drills_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """``GET /portfolios/{id}/rollup`` and ``GET /programs/{id}/rollup``,
    defaulting to the same resolved-per-request as-of the other routers use."""
    router = APIRouter(route_class=PageRoute)
    resolve = default_as_of if callable(default_as_of) else lambda: default_as_of

    @router.get("/portfolios/{portfolio_id}/rollup", response_class=HTMLResponse)
    def portfolio_drill(
        request: Request, portfolio_id: int, db: Db, as_of: date | None = None
    ) -> HTMLResponse:
        return _render(request, db, as_of or resolve(), "portfolio", portfolio_id)

    @router.get("/programs/{program_id}/rollup", response_class=HTMLResponse)
    def program_drill(
        request: Request, program_id: int, db: Db, as_of: date | None = None
    ) -> HTMLResponse:
        return _render(request, db, as_of or resolve(), "program", program_id)

    return router
