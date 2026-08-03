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

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

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
