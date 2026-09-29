"""One structured JSON line per HTTP request, on the ``driftless.request`` logger.

What a running deployment can be asked afterwards — "which requests failed, and
how slow were they?" — needs a record, and a record only helps if it parses, so
each line is JSON: timestamp, method, path, status, duration, client host and a
request id.

**It never carries a secret or a business figure.** The query string, the request
and response bodies and the ``Authorization`` header are absent by construction —
``request.url.path`` drops the query, and no header is ever read — because a
credential or a project's cost in a log line is a leak, and a log is copied to
places the database is not. There is nothing here to redact, so nothing to
forget to redact.

**The request id closes the loop the rest of the line cannot.** An operator
reading a 500 in the log has no way to tie it to the response a user actually
held, and a user reporting a failure has nothing to quote back. ``X-Request-ID``
is used here rather than a bespoke header because it is the header every
intermediary an operator already runs — nginx, an ALB, a browser devtools
network tab — already knows to surface, so the id an operator greps for is the
one already sitting in front of them. It is read from the inbound request when
the caller supplies one (so a request already carrying an id from an upstream
proxy keeps the same one end to end) and generated otherwise, then both logged
and echoed back on the response, so the id an operator greps is the id the user
can read off the failed call.

An inbound header is untrusted input reaching a JSON log line and a response
header, so it is validated rather than trusted: :data:`_REQUEST_ID_PATTERN`
accepts only a bounded run of characters that cannot break a JSON string or
smuggle a second log line, and anything outside that shape is replaced wholesale
with a generated id rather than escaped and echoed. Escaping would still hand a
caller-chosen string to the operator's log; replacing it means the log-forging
input never reaches a line at all.

This is an operational stream, not a second audit trail: the ChangeLog
(``driftless/db/changelog.py``) is the record of who changed what, and stays the
only one. Nothing here is read back by any surface, and the id is discarded once
the response leaves this process — it never reaches a rendered page or a report,
whose byte-identical regeneration at a pinned as-of would otherwise break the
moment two runs generated two different ids.

The module only emits — it never calls ``basicConfig`` and never sets a level, so
verbosity is entirely the operator's:

    logging.getLogger("driftless.request").setLevel(logging.INFO)

At the default level the lines cost a level check and nothing else.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import FastAPI, Request, Response

logger = logging.getLogger("driftless.request")

Next = Callable[[Request], Awaitable[Response]]

REQUEST_ID_HEADER = "X-Request-ID"

# Alphanumerics plus `-`/`_`: wide enough for a UUID, a ULID or an upstream
# proxy's own trace id, narrow enough that nothing in the set can close a JSON
# string, start a new line or otherwise reshape the log record it lands in. The
# length bound stops a caller from handing the log an unbounded string; 128 is
# comfortably past every id format above while still bounded.
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _request_id(request: Request) -> str:
    """The id this request is known by: the caller's, if it is one this module trusts.

    A hex UUID4 is generated for every other case — no inbound header, or one
    that fails :data:`_REQUEST_ID_PATTERN` — so a request always has exactly one
    id, and that id is never a string this process did not itself vouch for.
    """
    supplied = request.headers.get(REQUEST_ID_HEADER)
    if supplied is not None and _REQUEST_ID_PATTERN.fullmatch(supplied):
        return supplied
    return uuid.uuid4().hex


async def log_request(request: Request, call_next: Next) -> Response:
    """Serve the request, then emit its line. Never changes the response except
    to stamp the request id it also logs.

    The line is emitted in a ``finally``, because a route that raises returns no
    response at all: the error handler above this middleware answers 500, and a
    line written only on the way back would omit precisely the requests an
    operator opens the log to find. The exception still travels — logging a
    failure never swallows it. The id is resolved before that ``try`` for the
    same reason: a route that raises past ``call_next`` never returns a response
    here for this middleware to stamp a header onto directly, but it is stashed
    on ``request.state`` first, so the handler that does answer that response —
    above this middleware — can still stamp the same id the ``finally`` below
    logs, and it must be the same id a caller who supplied one used.
    """
    # Wall clock, deliberately: a duration and a timestamp are facts about this
    # process run, and they feed a log line only — never a rendered page or a
    # report, whose as-of stays an explicit input and whose output stays
    # byte-identical on regeneration.
    started = time.perf_counter()
    status = 500  # what the server answers when the route raises past us
    request_id = _request_id(request)
    # Stashed before `call_next` so a route that raises still leaves it reachable:
    # the exception handler above this middleware (`driftless/web/errors.py`,
    # registered for `Exception`) gets a *new* `Request` wrapping the same ASGI
    # scope, and `request.state` is backed by that scope, so it reads the id this
    # middleware resolved rather than having none to stamp on the 500 it answers.
    request.state.request_id = request_id
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    finally:
        if logger.isEnabledFor(logging.INFO):
            logger.info(
                json.dumps(
                    {
                        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                        "request_id": request_id,
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
