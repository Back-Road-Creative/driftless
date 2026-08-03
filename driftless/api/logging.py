"""One structured JSON line per HTTP request, on the ``driftless.request`` logger.

What a running deployment can be asked afterwards — "which requests failed, and
how slow were they?" — needs a record, and a record only helps if it parses, so
each line is JSON: timestamp, method, path, status, duration and client host.

**It never carries a secret or a business figure.** The query string, the request
and response bodies and the ``Authorization`` header are absent by construction —
``request.url.path`` drops the query, and no header is ever read — because a
credential or a project's cost in a log line is a leak, and a log is copied to
places the database is not. There is nothing here to redact, so nothing to
forget to redact.

This is an operational stream, not a second audit trail: the ChangeLog
(``driftless/db/changelog.py``) is the record of who changed what, and stays the
only one. Nothing here is read back by any surface.

The module only emits — it never calls ``basicConfig`` and never sets a level, so
verbosity is entirely the operator's:

    logging.getLogger("driftless.request").setLevel(logging.INFO)

At the default level the lines cost a level check and nothing else.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import FastAPI, Request, Response

logger = logging.getLogger("driftless.request")

Next = Callable[[Request], Awaitable[Response]]


async def log_request(request: Request, call_next: Next) -> Response:
    """Serve the request, then emit its line. Never changes the response.

    The line is emitted in a ``finally``, because a route that raises returns no
    response at all: the error handler above this middleware answers 500, and a
    line written only on the way back would omit precisely the requests an
    operator opens the log to find. The exception still travels — logging a
    failure never swallows it.
    """
    # Wall clock, deliberately: a duration and a timestamp are facts about this
    # process run, and they feed a log line only — never a rendered page or a
    # report, whose as-of stays an explicit input and whose output stays
    # byte-identical on regeneration.
    started = time.perf_counter()
    status = 500  # what the server answers when the route raises past us
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        if logger.isEnabledFor(logging.INFO):
            logger.info(
                json.dumps(
                    {
                        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                        "method": request.method,
                        "path": request.url.path,  # path only: the query string is not logged
                        "status": status,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                        "client": request.client.host if request.client else None,
                    }
                )
            )


def install_request_log(app: FastAPI) -> None:
    """Attach the request log to ``app`` — the app module's single wiring line."""
    app.middleware("http")(log_request)
