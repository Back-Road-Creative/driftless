"""A page-route 422 says what the reader can do (audit F-G4).

The wizard's apply refuses a blank narrative body with ``HTTPException(422)`` on a
page route, and ``web.errors`` carried no 422 wording, so the shell fell back to
"Something went wrong … the error has been logged" — the wording the team already
called misleading and fixed for the 403 in 6bf63cb. Nothing failed and nothing was
logged: the reader's own input was refused, and the reader can fix it. The page must
say so — and must still render none of the exception's detail, which may quote the
input itself.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from driftless.api.logging import REQUEST_ID_HEADER
from driftless.web.errors import PageRoute, install_page_errors

_DETAIL = "field 'body' of row 17 was blank"  # must never reach the page


def _page_app() -> FastAPI:
    router = APIRouter(route_class=PageRoute)

    @router.get("/refuse", response_class=HTMLResponse)
    def refuse() -> HTMLResponse:
        raise HTTPException(422, _DETAIL)

    app = FastAPI()
    app.include_router(router)
    install_page_errors(app)
    return app


def test_a_page_422_names_the_readers_own_input_not_a_logged_error() -> None:
    with TestClient(_page_app()) as client:
        page = client.get("/refuse")
    assert page.status_code == 422
    assert "text/html" in page.headers["content-type"]
    assert "error has been logged" not in page.text, "nothing was logged: input was refused"
    assert "Something went wrong" not in page.text
    assert "That submission does not parse" in page.text, "the refusal is named"
    assert "submit it again" in page.text, "and the reader is told the way back"
    assert "row 17" not in page.text, "the exception's detail still never renders"


def _raising_app() -> FastAPI:
    page_router = APIRouter(route_class=PageRoute)

    @page_router.get("/explode-page", response_class=HTMLResponse)
    def explode_page() -> HTMLResponse:
        raise RuntimeError("boom")

    api_router = APIRouter()

    @api_router.get("/explode-api")
    def explode_api() -> dict[str, str]:
        raise RuntimeError("boom")

    app = FastAPI()
    app.include_router(page_router)
    app.include_router(api_router)
    install_page_errors(app)
    return app


def test_a_page_500_omits_the_request_id_when_nothing_stashed_one() -> None:
    """No middleware ran ahead of this request, so `request.state` carries no id —
    the handler must omit the header rather than raise reading a missing one, which
    would turn a 500 into a crash."""
    with TestClient(_raising_app(), raise_server_exceptions=False) as client:
        page = client.get("/explode-page")
    assert page.status_code == 500
    assert REQUEST_ID_HEADER not in page.headers


def _stashing_middleware(app: FastAPI, request_id: str) -> None:
    """Stand in for `driftless.api.logging.log_request`: stash an id on `request.state`
    the way that middleware does, without pulling its whole request-log surface (JSON
    lines, `caplog`) into a test about the error handler alone."""

    async def _stash(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = request_id
        return await call_next(request)

    app.middleware("http")(_stash)


def test_a_page_500_carries_the_request_id_something_upstream_stashed() -> None:
    """`page_server_error` is the one handler that ever answers a raising route — it
    reads the id stashed on `request.state` before `call_next`, so the response a
    user holds carries the same id the log line does."""
    app = _raising_app()
    _stashing_middleware(app, "stashed-for-test")
    with TestClient(app, raise_server_exceptions=False) as client:
        page = client.get("/explode-page")
    assert page.status_code == 500
    assert page.headers[REQUEST_ID_HEADER] == "stashed-for-test"


def test_a_json_500_is_the_same_handler_as_the_page_one_and_also_carries_the_id() -> None:
    """The API 500 is not a second handler: `page_server_error` branches on the surface
    but stamps both branches from the same `request.state` read, so a non-page route
    that raises gets the header exactly as a page one does."""
    app = _raising_app()
    _stashing_middleware(app, "stashed-for-test")
    with TestClient(app, raise_server_exceptions=False) as client:
        api = client.get("/explode-api")
    assert api.status_code == 500
    assert api.headers[REQUEST_ID_HEADER] == "stashed-for-test"
