"""``GET /metrics`` in Prometheus text-exposition format -- gated like every other route.

A scraper endpoint is conventionally left uncredentialed. That is wrong here:
driftless manages real businesses' portfolios, and the rule
:mod:`driftless.api.logging` states for the request log -- a line "never
carries a secret or a business figure ... a credential or a project's cost in
a log line is a leak" -- applies just as much to a row count like
``driftless_projects_total`` disclosed on an open port. So this is wired the
way :func:`driftless.api.logging.install_request_log` already is -- one
middleware, one call from ``app.py`` -- and the route adds **no** exemption to
:func:`driftless.api.secure.is_open_path`. An ordinary authenticated ``GET``
is exactly the access this needs.

**HTTP shape only, enforced by what this module can reach, not by a convention
a reviewer has to remember.** Neither function below takes a
:class:`~sqlalchemy.orm.Session`, and nothing here imports
:mod:`driftless.models` or :mod:`driftless.db` -- a business figure cannot
reach :func:`render` without a new import this file does not have. What is
emitted: a request counter and a cumulative duration, labelled by method,
status and the matched route *template* (``/projects/{project_id}``, never
``/projects/482`` -- the raw path would let an id space explode the label
set), plus process uptime.

**What these counters do NOT see.** :class:`driftless.api.secure.TokenGate` wraps
the whole app from *outside* and answers a refused request itself, without ever
calling inward -- so the middleware below never runs for one. Every 401 and 403
the gate issues is therefore absent from ``driftless_http_requests_total``, and a
burst of rejected credentials looks identical here to no traffic at all. That is
a property of where the gate sits, not an oversight. Note the request log
(:mod:`driftless.api.logging`) is installed the same way and so has the same
blind spot -- a refused request is currently recorded in neither, which is a gap
worth closing at the gate itself rather than by moving either middleware out.

**Concurrency.** The counters are process-global dicts, incremented by an ASGI
middleware that ``TestClient`` -- and uvicorn, for real -- can run for more
than one request at once. Every read-modify-write against :data:`_COUNTS` and
:data:`_DURATION_SECONDS` happens inside :data:`_LOCK`; :func:`render` takes
the same lock to copy them out, so a scrape never observes a family mid-update.
Nothing here resets either dict -- a metrics endpoint that lost its running
total would not be one.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

Next = Callable[[Request], Awaitable[Response]]

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"  # the Prometheus exposition format

_START = time.monotonic()
_LOCK = threading.Lock()
# (method, status, route template) -> running total / cumulative seconds. Never
# the raw path -- see the module docstring's cardinality note.
_COUNTS: dict[tuple[str, str, str], int] = {}
_DURATION_SECONDS: dict[tuple[str, str, str], float] = {}


def _route_template(request: Request) -> str:
    """The matched route's own path pattern, or ``"unmatched"`` for a 404.

    Read off ``request.scope["route"]`` *after* ``call_next`` has run the whole
    routing table -- that is the only point this middleware sees what Starlette
    matched. A request that matched nothing carries no route at all, and the
    fixed label is what stops a scan of garbage paths from minting a label of
    its own, which is precisely what a route template exists to prevent.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


async def _record(request: Request, call_next: Next) -> Response:
    """Time and count the request, then hand its response back unchanged."""
    started = time.perf_counter()
    status = 500  # what an exception past this middleware means -- see install_request_log
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        elapsed = time.perf_counter() - started
        key = (request.method, str(status), _route_template(request))
        with _LOCK:
            _COUNTS[key] = _COUNTS.get(key, 0) + 1
            _DURATION_SECONDS[key] = _DURATION_SECONDS.get(key, 0.0) + elapsed


def _escape(label: str) -> str:
    """Prometheus's own label-value escaping, in the order its format requires."""
    return label.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render() -> str:
    """The current counters as Prometheus text-exposition.

    Snapshotted under :data:`_LOCK` and formatted outside it, so a scrape holds
    the lock only long enough to copy two dicts, never for the string-building.
    """
    with _LOCK:
        counts = sorted(_COUNTS.items())
        durations = sorted(_DURATION_SECONDS.items())
    lines = [
        "# HELP driftless_http_requests_total Total HTTP requests served.",
        "# TYPE driftless_http_requests_total counter",
        *(
            f'driftless_http_requests_total{{method="{m}",status="{s}",route="{_escape(r)}"}} {n}'
            for (m, s, r), n in counts
        ),
        "# HELP driftless_http_request_duration_seconds_sum "
        "Cumulative seconds spent answering requests.",
        "# TYPE driftless_http_request_duration_seconds_sum counter",
        *(
            f'driftless_http_request_duration_seconds_sum{{method="{m}",status="{s}",'
            f'route="{_escape(r)}"}} {t:.6f}'
            for (m, s, r), t in durations
        ),
        "# HELP driftless_process_uptime_seconds Seconds since this process started serving.",
        "# TYPE driftless_process_uptime_seconds gauge",
        f"driftless_process_uptime_seconds {time.monotonic() - _START:.3f}",
        "",
    ]
    return "\n".join(lines)


async def _metrics() -> Response:
    return PlainTextResponse(render(), media_type=CONTENT_TYPE)


def install_metrics(app: FastAPI) -> None:
    """Attach the counter middleware and the ``/metrics`` route -- the app
    module's single wiring line.

    Gated exactly like every other route: :class:`driftless.api.secure.TokenGate`
    wraps ``app`` in front of this, and this module adds nothing to
    ``is_open_path``. A GET needs no more than the ordinary authenticated role.
    """
    app.middleware("http")(_record)
    app.add_api_route("/metrics", _metrics, methods=["GET"], include_in_schema=False)
