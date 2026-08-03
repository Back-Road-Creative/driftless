"""The request log has to carry the requests that failed.

`tests/test_api_logging.py` pins the happy path and the redaction contract; this
file pins the case an operator actually opens the log for. A raising route is
answered 500 from above the middleware, so a line emitted only after ``call_next``
returned omits exactly the requests worth reading. The app is built here rather
than imported — a deliberately exploding route does not belong on the service's.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from driftless.api.logging import install_request_log

LOGGER = "driftless.request"


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("the route exploded")

    install_request_log(app)
    return app


def _lines(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [json.loads(record.getMessage()) for record in caplog.records if record.name == LOGGER]


def test_a_raising_route_still_emits_one_line_with_the_status_served(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    client = TestClient(_app(), raise_server_exceptions=False)

    assert client.get("/boom").status_code == 500
    (line,) = _lines(caplog)
    assert line["status"] == 500 and line["path"] == "/boom" and line["method"] == "GET"
    assert isinstance(line["duration_ms"], float) and line["duration_ms"] >= 0


def test_logging_a_failure_does_not_swallow_it(caplog: pytest.LogCaptureFixture) -> None:
    """The middleware still never changes what the app does — the error propagates."""
    caplog.set_level(logging.INFO, logger=LOGGER)
    client = TestClient(_app())

    with pytest.raises(RuntimeError, match="the route exploded"):
        client.get("/boom")
    assert [line["status"] for line in _lines(caplog)] == [500]
