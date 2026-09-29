"""The search page: ``GET /search?q=…`` — one field, results grouped by kind. The page owns the
human path and the JSON endpoint takes the extra segment, the ``/projects/{id}/hub`` convention
mirrored (``api.search``'s note; ``tests/test_web_routes_not_shadowed.py``). Renders
``api.search.search`` and adapts nothing — the grouping keeps its order, so page and endpoint
cannot disagree. No as-of, no clock: nothing here is dated."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from driftless.api.deps import Db
from driftless.api.search import PER_KIND, Hit, search
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES


def create_search_router() -> APIRouter:
    """``GET /search``: the search field, and the hits grouped under one table per kind."""
    router = APIRouter(route_class=PageRoute)

    @router.get("/search", response_class=HTMLResponse)
    def search_page(request: Request, db: Db, q: str = "") -> HTMLResponse:
        groups: dict[str, list[Hit]] = {}
        for hit in search(db, q):
            groups.setdefault(hit.kind, []).append(hit)
        context = {"q": q, "groups": groups, "cap": PER_KIND}
        return TEMPLATES.TemplateResponse(request, "search.html", context)

    return router
