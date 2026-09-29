"""The method-profile library as pages: ``GET /methods`` and ``GET /methods/{key}``.

Mirrors :mod:`driftless.web.techniques` in shape: ``driftless.pmbok.methods.METHODS``
is a frozen registry, so this router reads no store and takes no as-of — what
it renders is identical on every request. Keyed by the profile's own key
(``"scrum"``, ``"kanban"``) rather than a derived slug: both keys are already
one plain word, so there is no separate slug formula to keep in step with a
display name the way the technique library needs one.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from driftless.pmbok.method_content import CONTENT
from driftless.pmbok.methods import METHODS
from driftless.pmbok.practice_content import CONTENT as PRACTICE_CONTENT
from driftless.web.errors import PageRoute
from driftless.web.related import for_practice
from driftless.web.templating import TEMPLATES

#: Which method's page may link to a project's own board, and at what route —
#: the same "only to a route that exists" rule the technique page follows for
#: its assist links. Scrum has no sprint-specific view of its own yet, so it
#: carries no entry and its page never fabricates a link.
_PROJECT_ROUTES: dict[str, str] = {"kanban": "/projects/{project_id}/board"}


def create_methods_router() -> APIRouter:
    """The two method-library pages. No as-of: neither reads a store or a date."""
    router = APIRouter(route_class=PageRoute)

    @router.get("/methods", response_class=HTMLResponse)
    def method_index(request: Request) -> HTMLResponse:
        """Every method profile Driftless describes, each carrying its own plain
        summary so the index answers "what is this?" before a reader follows a link.

        The coverage count above the list splits the same rows by the model's own
        crosswalk vocabulary: a method is "fully crosswalked" only if every one of
        its practices names a PMBOK-6 process or technique (``Practice.crosswalk``);
        otherwise it carries at least one practice whose crosswalk is deliberately
        empty and excused by a ``crosswalk_reason`` — "guide-only" here.
        """
        methods = sorted(METHODS.values(), key=lambda m: m.display_name)
        fully_crosswalked = sum(
            1 for method in methods if all(practice.crosswalk for practice in method.practices)
        )
        return TEMPLATES.TemplateResponse(
            request,
            "methods.html",
            {
                "methods": methods,
                "fully_crosswalked_count": fully_crosswalked,
                "guide_only_count": len(methods) - fully_crosswalked,
            },
        )

    @router.get("/methods/{key}", response_class=HTMLResponse)
    def method_detail(request: Request, key: str, project: int | None = None) -> HTMLResponse:
        """One method in full: its practices grouped by kind, each with its own
        crosswalk to the PMBOK-6 processes or techniques it most nearly resembles,
        plus its working material. With ``?project=`` and a route this method
        actually has, it also links that project's own board."""
        method = METHODS.get(key)
        if method is None:
            raise HTTPException(404, f"unknown method: {key}")
        related = {practice.key: for_practice(practice.key) for practice in method.practices}
        route = _PROJECT_ROUTES.get(key)
        project_href = route.format(project_id=project) if route and project is not None else None
        return TEMPLATES.TemplateResponse(
            request,
            "method_detail.html",
            {
                "method": method,
                "related": related,
                "content": CONTENT.get(key, ()),
                "practice_content": PRACTICE_CONTENT,
                "project_href": project_href,
            },
        )

    return router
