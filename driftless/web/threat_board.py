"""The ranked live-threat board: ``GET /threats``.

Carved out of ``web/pages.py`` as the second slice of that split. It reads and renders
only — suppression and cross-store ranking belong to the assess engine (``top_threats``),
and the card build (``threat_cards``) joins each threat to its project and actions — so
none of the write path, the CSRF pair rule or the sign-off redirect table came with it.

``/sign-off`` is a module of its own now (``web/sign_off.py``) and still falls back to
``/threats``: that target is a path literal in an allowlist, not an import, so the two
modules share nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from driftless.api.deps import Db
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES
from driftless.web.views import threat_cards

# The threat board slices the ranked feed into fixed pages so a large board stays
# readable; the template groups each page's cards by project (finding #22). It lives
# beside the route that reads it, so a caller patching it patches the one the board
# consults.
THREATS_PER_PAGE = 15


def create_threat_board_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The threat board, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/threats", response_class=HTMLResponse)
    def threats(
        request: Request, db: Db, page: int = 1, at: date = Depends(resolve_as_of)
    ) -> HTMLResponse:
        """The ranked live-threat board, grouped by project and paginated.

        Each card names its project and links it to the project's process map, and
        lists the recommended PMBOK actions its assessment attached, so the board
        goes from "what is wrong" to "which project and what to do". Suppression and
        cross-store ranking stay with the assess engine (``top_threats``); the card
        build (``threat_cards``) only joins each threat to its project and actions.
        The ranked feed is sliced into ``THREATS_PER_PAGE`` pages BEFORE the template
        groups a page's cards by project — slicing keeps the ranked order, so the
        template only reshapes what it is handed. ``page`` is clamped into range, so
        an out-of-bounds page lands on a valid one. Reads are pure functions of the
        store and the as-of date, so a double fetch is byte-identical.
        """
        ranked = threat_cards(db, at)
        total_pages = max(1, -(-len(ranked) // THREATS_PER_PAGE))
        page = max(1, min(page, total_pages))
        start = (page - 1) * THREATS_PER_PAGE
        context = {
            "as_of": at.isoformat(),
            "threats": ranked[start : start + THREATS_PER_PAGE],
            "page": page,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        }
        return TEMPLATES.TemplateResponse(request, "threats.html", context)

    return router
