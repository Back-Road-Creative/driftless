"""Designed HTML error pages — for the web surfaces, and only for them.

A page router builds its routes with ``route_class=PageRoute``, which stamps
``PAGE_SCOPE_KEY`` on the request scope before the endpoint runs — and therefore
before request validation, which runs inside that endpoint. The handlers
:func:`install_page_errors` registers read that stamp, so HTML-or-JSON is keyed
on the *surface the request matched* — never on an ``Accept`` header a browser
and a client can both send, for as long as there is a surface to read. A request
that matched an API route carries no stamp, so every JSON API response, error
bodies included, is byte-for-byte what it was before this module existed.
:func:`_is_page_surface` is where all three handlers ask the question, the one
place the answer is decided, and where the single exception — an address that
matched no route at all, and so addressed no surface — is spelled out.

Four refusals a browser can actually reach get a designed page: an address that
names nothing (404), a form left open until its CSRF pair went stale (403), a
form whose input a page endpoint refused (422 — both refusals the reader can
fix, so both say how), and anything else (500). No page
renders anything about the exception: no traceback, no query, no SQL, no detail
string. The 500 handler is registered for ``Exception``, which Starlette's
``ServerErrorMiddleware`` re-raises after the handler returns — the error still
reaches the logs and a default test client still sees it raised.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import FastAPI
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from driftless.web.templating import TEMPLATES

PAGE_SCOPE_KEY = "driftless_page"

# Fixed per status: the exception's own detail is never rendered, so a message can
# never carry a row id, a query or a stack.
_NOT_FOUND = ("Page not found", "That address does not match anything in this store.")
_EXPIRED = (
    "That form expired",
    "The page had been open too long to submit safely. Reload the page and submit it again.",
)
_DEFAULT = ("Something went wrong", "The page could not be rendered. The error has been logged.")
# The gate's 403, which is a different refusal from the expired form: this reader is
# signed in and simply may not write. Both live here so the two cannot drift apart.
_READ_ONLY = (
    "That is a read-only account",
    "You are signed in as a viewer, so you can read every page here but cannot change "
    "anything. Ask an admin for contributor access.",
)
# 405: the address is real and the method is not — its own wording, because the default
# says the error was logged and a refused method logs nothing.
_METHOD = (
    "That address does not do that",
    "The page is real, but it does not accept what the browser just sent. Go back to it "
    "and load it again.",
)
# 422: a page endpoint refused the reader's own input. Nothing failed and nothing was
# logged, so the default's "the error has been logged" is the same misleading wording
# the 403 shed — and the detail (which may quote the input) still never renders.
_UNPROCESSABLE = (
    "That submission does not parse",
    "Something sent in the form is not what its field takes — blank where prose is "
    "required, or a value of the wrong shape. Go back, adjust it and submit it again.",
)
_MESSAGES = {404: _NOT_FOUND, 403: _EXPIRED, 405: _METHOD, 422: _UNPROCESSABLE}
_HTML = "text/html"


class PageRoute(APIRoute):
    """An HTML page route: stamps the scope so the error handlers know the surface."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        endpoint = super().get_route_handler()

        async def stamped(request: Request) -> Response:
            request.scope[PAGE_SCOPE_KEY] = True
            return await endpoint(request)

        return stamped


def _is_page_surface(request: Request) -> bool:
    """Whether this refusal belongs to the HTML surface. Three readings, in order.

    1. The stamp, when the page's own endpoint ran — validation errors included, since
       validation happens inside it.
    2. The matched route, when it did not: a 405 is raised by the router *before* any
       endpoint, so nothing stamped the scope, yet the route the request matched is
       right there on it and says exactly which surface was addressed. Any other route —
       an API one — is JSON, whatever the caller says it accepts, which is what keeps
       every API body byte-for-byte what it was.
    3. Only when the request matched NO route at all does the caller's ``Accept`` decide.
       This is the one place the header is honest: there is no surface to read, because
       nothing was addressed. ``/projects/1/boardz`` is one letter off a real page and
       matches no pattern any table can hold, so the alternative is handing a person who
       typed an address the JSON default. A script asks with ``*/*`` or with no header at
       all — curl's shape — and neither of those asked for a page, so both keep the JSON.
    """
    if request.scope.get(PAGE_SCOPE_KEY):
        return True
    route = request.scope.get("route")
    if route is not None:
        return isinstance(route, PageRoute)
    return _HTML in request.headers.get("accept", "")


def _page(request: Request, status: int, wording: tuple[str, str] | None = None) -> Response:
    title, message = wording or _MESSAGES.get(status, _DEFAULT)
    context = {"status": status, "title": title, "message": message}
    return TEMPLATES.TemplateResponse(request, "error.html", context, status_code=status)


def read_only_page(request: Request) -> Response:
    """The 403 a signed-in viewer's write earns — rendered for the credential gate.

    That gate runs outside the app, so its refusal reaches none of the handlers below;
    it calls this instead of building its own response, which is what keeps one place
    deciding what a refusal page says.
    """
    return _page(request, 403, _READ_ONLY)


async def page_http_exception(request: Request, exc: Exception) -> Response:
    """An HTTPException on a page renders the shell; on the API, FastAPI's own JSON."""
    assert isinstance(exc, StarletteHTTPException)
    if _is_page_surface(request):
        return _page(request, exc.status_code)
    return await http_exception_handler(request, exc)


async def page_validation_error(request: Request, exc: Exception) -> Response:
    """A page address that does not parse renders the 404 shell — **status 404, not
    the 422 the API answers, and that is deliberate**.

    ``/projects/abc/hub`` is a browser address whose ``project_id`` is not a number,
    so it names no page that exists; 404 is the reading a reader can act on, and it
    is what every other unreachable address on the web surface already answers. A
    ``RequestValidationError`` is not an ``HTTPException``, so without this handler
    neither of the others saw it and the browser got a raw JSON validation dump.
    Every other surface keeps FastAPI's own body, byte for byte.
    """
    if _is_page_surface(request):
        return _page(request, 404)
    assert isinstance(exc, RequestValidationError)
    return await request_validation_exception_handler(request, exc)


async def page_server_error(request: Request, exc: Exception) -> Response:
    """An unhandled error on a page renders the shell; on the API, Starlette's own body."""
    if _is_page_surface(request):
        return _page(request, 500)
    return PlainTextResponse("Internal Server Error", status_code=500)


def install_page_errors(app: FastAPI) -> None:
    """Register all three handlers on ``app`` — call it once, after the routers are in."""
    app.add_exception_handler(StarletteHTTPException, page_http_exception)
    app.add_exception_handler(RequestValidationError, page_validation_error)
    app.add_exception_handler(Exception, page_server_error)
