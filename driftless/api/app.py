"""CRUD over the hierarchy: business -> portfolio -> program -> project -> workstream -> task.

Nothing binds a socket or opens an engine at import time — the session arrives
as a dependency, so a test can hand the app a throwaway database. Reads take no
request body, so one generic pair serves every entity — which is also why every
list endpoint takes ``?format=csv`` for free (driftless/api/export.py). A
create's body type is exactly what FastAPI validates against, so those stay
written out. Updates are
registered generically too — their body types are *generated* patch twins, so
there is nothing to write out and the annotation is attached at registration.

What a write must be true for, rather than shaped like, lives in
``driftless.api.rules``: this module decides which rules hang off which route,
and that module decides what each one means.
"""

import json
import logging
import os
from calendar import monthrange
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from sqlalchemy import text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from driftless import __version__
from driftless.api import calendar, schemas as s
from driftless.api.assembly import install_page_errors, mount_web
from driftless.assess import adapters
from driftless.api.deps import (  # alias: re-export
    Db,
    get_session as get_session,
    is_agent_actor,
    resolved_actor,
    signer,
)
from driftless.api.resources import register_resources
from driftless.api.export import Format, csv_response
from driftless.api.logging import install_request_log
from driftless.api.metrics import install_metrics
from driftless.api.idempotency import install_idempotency
from driftless.api.openapi import install_api_only_openapi
from driftless.api.records import fetch, insert
from driftless.api.rules import (
    require_department_in_business,
    require_matching_unit,
    require_program_in_portfolio,
)
from driftless.api.search import Hit, search
from driftless.api.versioning import install_versioned_api
from driftless.web import errors as web_errors
from driftless.services.sign_offs import create_sign_off
from driftless.services.status_snapshots import create_status_snapshot
from driftless.services.technique_runs import (
    UnknownProcessError,
    UnknownTechniqueError,
    record_run,
)
from driftless.pmbok.provenance import MethodContext
from driftless.db.schema_version import EXPECTED_REVISION, SchemaAheadError, schema_is_ahead
from driftless.db.session import session_scope
from driftless.models import (
    Business,
    Department,
    Person,
    TechniqueRun,
    Portfolio,
    Program,
    Project,
    SignOff,
    StatusSnapshot,
    Task,
    Workstream,
)

logger = logging.getLogger("driftless.api")


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    """The one thing that happens before the first request: :func:`refuse_if_schema_ahead`.

    A lifespan rather than a route dependency or a first-request hook, because
    the whole point is that no request is served against a schema this image
    cannot read — uvicorn logs the failure and exits, and an orchestrator holds a
    failed image out of rotation. Nothing opens a store at *import* time still:
    this runs when the server starts, so a test importing the app pays nothing."""
    refuse_if_schema_ahead()
    yield


# Documents the real gate (:class:`driftless.api.secure.TokenGate`) to a generated
# client, without adding a second gate that could disagree with it: ``auto_error=False``
# makes this dependency incapable of ever refusing a request -- read its source, it has
# no branch that raises -- so it can only describe the policy TokenGate enforces, never
# enforce a different one. Attached globally, the same way TokenGate wraps the whole
# app instead of gating each route, so a route added later is described with no
# per-registration edit.
_BEARER_CREDENTIAL = HTTPBearer(
    scheme_name="DriftlessBearerToken",
    description="A DRIFTLESS_API_TOKEN, a per-user dfl_... token, or a signed session "
    "cookie -- driftless.api.secure.TokenGate is what actually checks it.",
    auto_error=False,
)


ALLOW_SCHEMA_AHEAD_ENV = "DRIFTLESS_ALLOW_SCHEMA_AHEAD"  # the startup refusal's one override


# Fixed wording for a page-surface 409, in the idiom of ``web.errors._MESSAGES``:
# the exception is never rendered, so no constraint name, SQL or row can leak.
_CONFLICT = (
    "That was already recorded",
    "The store already holds an entry for exactly that — most often a weekly status "
    "filed for a date that already has one. Go back to the page: the existing entry "
    "is already on it.",
)


def _on_integrity_error(request: Request, exc: IntegrityError) -> Response:
    """Turn a database constraint violation into a 409, not a 500.

    An ``IntegrityError`` is by definition the request's data conflicting with a
    constraint — a duplicate on a unique index, a cross-field CHECK the upstream
    schema cannot see (a window whose end precedes its start), a foreign key not
    pre-checked. That is a client conflict, so it answers 409 rather than a bare
    500. The SQL text is deliberately not echoed back.

    The answer speaks the surface's language, keyed exactly the way every refusal
    in :mod:`driftless.web.errors` is keyed — on the surface the request matched,
    never on an ``Accept`` header. A browser reaches this through everyday form
    posts with no pre-check (refiling the weekly status for an already-snapshotted
    date, the wizard writing a narrative kind twice), and raw JSON with no
    navigation is a dead end there; the designed shell is not. A request that
    matched an API route carries no page stamp, so every API error body stays
    byte-for-byte what it was.
    """
    if web_errors._is_page_surface(request):
        return web_errors._page(request, 409, _CONFLICT)
    return JSONResponse(status_code=409, content={"detail": "constraint violation"})


def _applied_revision(db: Session) -> str | None:
    """The Alembic revision stamped on the store, or ``None`` if never migrated."""
    connection = db.connection()
    if not sa_inspect(connection).has_table("alembic_version"):
        return None
    return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()


def refuse_if_schema_ahead() -> None:
    """Refuse to serve when the store is stamped past this image (OPERATIONS.md).

    Detecting that on ``/health/ready`` was never enough: an image older than the
    applied migration reads *and writes* a schema it does not understand, and by
    the time anyone reads the probe the data is already wrong. So the unrunnable
    state refuses to run. *Behind* is deliberately not fatal — deploy the code,
    then migrate is the ordinary order — and neither is an unstamped
    ``create_all`` store, which is what dev and the suite build.

    Read through ``session_scope``, the app's own factory, so this and the first
    request share one engine and one way of reading the stamp.

    Two ways out, both deliberate. Any failure to *reach* the store is logged and
    tolerated: an outage is the readiness probe's question, and a boot that
    crash-loops on an unrelated failure is a worse outage than the one it was
    guarding against. And ``DRIFTLESS_ALLOW_SCHEMA_AHEAD=1`` starts anyway for a
    deliberate, verified-compatible rollback — logged loudly every single start,
    because an override nobody can see is how a temporary one becomes permanent.
    """
    try:
        with session_scope() as db:
            applied = _applied_revision(db)
    except Exception as exc:  # noqa: BLE001 -- see above: unreachable is readiness's job
        # The type only: driver text can carry the DSN, and the same "leaks nothing"
        # rule the probe's bodies follow applies to a log an operator pastes around.
        logger.warning("the schema check could not read the store (%s).", type(exc).__name__)
        return
    if not schema_is_ahead(applied):
        return
    trouble = (
        f"the database is stamped with revision {applied}, which this image has never heard "
        f"of; it requires {EXPECTED_REVISION}, and no forward migration repairs that"
    )
    if os.environ.get(ALLOW_SCHEMA_AHEAD_ENV) == "1":
        logger.warning("%s. Serving anyway: %s=1.", trouble, ALLOW_SCHEMA_AHEAD_ENV)
        return
    raise SchemaAheadError(
        f"refusing to serve — {trouble}. Deploy the image that matches, or restore the "
        f"pre-upgrade dump (OPERATIONS.md, Rolling back). {ALLOW_SCHEMA_AHEAD_ENV}=1 starts "
        f"anyway, for a rollback whose compatibility you have verified."
    )


def health(db: Db) -> JSONResponse:
    """Can this instance serve? The store is asked, because the answer depends on it.

    This is what ``docker-compose.yml``'s healthcheck calls, and what it is asking
    is readiness, not liveness — an operator reading ``docker compose ps`` wants to
    know whether the service *works*, and a process that is up but cannot reach its
    database does not. It answered from a byte literal before auth and without a
    store for one release, and stayed green straight through a Postgres outage; the
    first signal anyone got was a user complaint. So it does the one thing that
    makes the answer true.

    **Cost.** One ``SELECT 1`` on a connection the pool already holds, every
    ``interval``, forever. Nothing here reads a row, counts one, or opens a
    transaction that outlives the statement — a probe that walks the store is a
    self-inflicted load test on a schedule.

    **Not schema currency.** *Ahead* already refuses to start
    (:func:`refuse_if_schema_ahead`), so no request is served against it at all and
    reporting it here would be answering a question the process cannot be alive to
    ask; *behind* is the ordinary deploy-then-migrate state and serves fine. The
    remaining reason is disclosure: this route is outside the credential gate
    (:mod:`driftless.api.secure`), and revision numbers are exactly what
    ``/health/ready`` sits inside the gate to keep from anonymous callers.

    **Leaks nothing**, for the same reason. Both bodies are literals, and the log
    line carries ``type(exc).__name__`` and nothing else — driver text can carry a
    DSN, and the caller is anyone who can reach the port.
    """
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("the store did not answer the health probe (%s).", type(exc).__name__)
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
    return JSONResponse(status_code=200, content={"status": "ok"})


def health_ready(db: Db) -> JSONResponse:
    """Readiness: the database answers *and* carries the schema this code requires.

    A different question from :func:`health`, so it is a different route: that one
    asks whether the store answers and says only that, which is why it can stay
    outside the gate. This one adds the revision the store carries, and a revision
    number is not something to hand an anonymous caller — so it sits **inside** the
    gate, and an orchestrator that wants it sends the bearer token.

    Nothing from the exception reaches the body — the three failure phrasings
    are literals, so a DSN, a password or driver text cannot leak by accident.
    ``ahead`` means the database is stamped with a revision this image has never
    heard of, which no forward migration repairs (OPERATIONS.md, Rolling back) —
    the same :func:`schema_is_ahead` the startup refusal reads, so a store cannot
    be fatal at boot and merely behind here. Reachable at all only with the
    override set: without it, :func:`refuse_if_schema_ahead` already exited.
    """
    try:
        applied = _applied_revision(db)
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"detail": "database unreachable"})
    if applied == EXPECTED_REVISION:
        return JSONResponse(status_code=200, content={"detail": "ready"})
    detail = "schema ahead" if schema_is_ahead(applied) else "schema behind"
    return JSONResponse(status_code=503, content={"detail": detail})


def create_business(payload: s.BusinessIn, db: Db) -> Business:
    return insert(db, Business, payload)


def create_portfolio(payload: s.PortfolioIn, db: Db) -> Portfolio:
    return insert(db, Portfolio, payload, business_id=Business)


def create_program(payload: s.ProgramIn, db: Db) -> Program:
    return insert(db, Program, payload, portfolio_id=Portfolio)


def create_project(payload: s.ProjectIn, db: Db) -> Project:
    require_program_in_portfolio(db, payload.portfolio_id, payload.program_id)
    require_department_in_business(db, payload.portfolio_id, payload.responsible_department_id)
    return insert(
        db,
        Project,
        payload,
        portfolio_id=Portfolio,
        program_id=Program,
        responsible_department_id=Department,
    )


def create_workstream(payload: s.WorkstreamIn, db: Db) -> Workstream:
    return insert(db, Workstream, payload, project_id=Project)


def create_task(payload: s.TaskIn, db: Db) -> Task:
    require_matching_unit(db, payload.workstream_id, payload.estimate_unit)
    return insert(db, Task, payload, assignee_id=Person)


def post_status_snapshot(request: Request, payload: s.StatusSnapshotIn, db: Db) -> StatusSnapshot:
    """File a weekly snapshot through the service both write surfaces share.

    The handler is the HTTP shape only; the write itself -- and the rule that the
    completion figure is computed, never accepted from the request -- lives in
    :func:`driftless.services.status_snapshots.create_status_snapshot`, which the
    status page calls too. ``resolved_actor`` hands in the identity ``Db`` already
    resolved rather than the service re-deriving it.
    """
    return create_status_snapshot(db, payload, resolved_actor(request))


def post_sign_off(request: Request, payload: s.SignOffIn, db: Db) -> SignOff:
    """Append a decision through the service both write surfaces share.

    The handler is the HTTP shape plus the one thing a service cannot do: decide who
    signed. The posted ``signed_by`` is a claim — :func:`driftless.api.deps.signer`
    resolves the gate's principal over it here, once, and hands the answer to
    :func:`driftless.services.sign_offs.create_sign_off`, which the browser form calls
    too. So the form cannot hold a weaker guarantee than the JSON route. Same for
    ``is_agent_actor``: the service refuses an agent's decision by default, and both
    surfaces resolve that flag the same way.
    """
    return create_sign_off(
        db, payload, signer(request, payload.signed_by), is_agent=is_agent_actor(request)
    )


def post_technique_run(request: Request, payload: s.TechniqueRunIn, db: Db) -> TechniqueRun:
    """Append one provenance row through :func:`record_run`, the ledger's one writer,
    so the JSON route can refuse nothing less than the browser forms do — an unknown
    technique or process is a 422 here exactly as it is on the decisions page."""
    try:
        return record_run(
            db,
            project_id=payload.project_id,
            technique_key=payload.technique_key,
            process_id=payload.process_id,
            actor=payload.actor,
            as_of=payload.as_of,
            method=MethodContext(payload.method),
            source_version=payload.source_version,
            inputs_snapshot=json.loads(payload.inputs_snapshot),
            outputs_produced=json.loads(payload.outputs_produced),
        )
    except (UnknownTechniqueError, UnknownProcessError) as error:
        raise HTTPException(422, str(error)) from error


def calendar_feed(db: Db) -> Response:
    """Every dated record in the store as a subscribable iCalendar feed —
    :mod:`driftless.api.calendar` holds the decisions. Registered directly on ``app`` for
    the reason ``/search/results`` is: an included router's routes are walked as *pages*,
    and ``text/calendar`` is not HTML. It answers a ``Response``, so it has no list
    response model and stays outside the both-formats export walk — a calendar has one
    encoding, and ``?format=csv`` on it would mean nothing."""
    return calendar.feed(db, "driftless")


def project_calendar_feed(project_id: int, db: Db) -> Response:
    """One project's dates, at an address that means that project for good."""
    return calendar.feed(db, fetch(db, Project, project_id).name, project_id)


def _period_ends(start: date, as_of: date) -> list[date]:
    """Month-end dates from ``start`` through ``as_of``, ``as_of`` ALWAYS last --
    even when it is not itself a month-end -- so a caller asking for a period
    series never has to guess whether its own as-of made the list."""
    ends: list[date] = []
    year, month = start.year, start.month
    while True:
        month_end = date(year, month, monthrange(year, month)[1])
        if month_end >= as_of:
            break
        if month_end >= start:
            ends.append(month_end)
        month, year = (1, year + 1) if month == 12 else (month + 1, year)
    ends.append(as_of)
    return ends


def project_ev_series(project_id: int, db: Db, as_of: date) -> Response:
    """One earned-value snapshot per period from the project's plan baseline start
    through ``as_of`` -- a period series shaped for IPMDAR-style cost reporting,
    computed through :func:`adapters.project_snapshot`, the one canonical EVM
    loader every other surface (dashboard, reports, assessment) already reads, so
    this can never disagree with them about what CPI was on a given date.

    Keys sorted and rendered with no whitespace choice left to a library default,
    so the same store and the same ``as_of`` answer byte-identically every time --
    no clock, no set-ordering, nothing read off the environment."""
    project = fetch(db, Project, project_id)
    baseline = adapters.plan_baseline(project, as_of)
    start = (
        min((line.planned_start for line in baseline.lines), default=as_of) if baseline else as_of
    )
    start = min(start, as_of)
    rows = []
    for period_end in _period_ends(start, as_of):
        snap = adapters.project_snapshot(db, project, period_end)
        rows.append(
            {
                "period_end": period_end.isoformat(),
                "bac": snap.bac,
                "pv": snap.pv,
                "ev": snap.ev,
                "ac": snap.ac,
                "cpi": snap.cpi,
                "spi": snap.spi,
                "eac": snap.eac,
                "etc": snap.etc,
                "vac": snap.vac,
                "cv": snap.cv,
                "sv": snap.sv,
            }
        )
    return Response(json.dumps(rows, sort_keys=True), media_type="application/json")


def search_results(db: Db, q: str = "", format: Format = "json") -> Any:
    """Cross-entity search for scripts and agents — :mod:`driftless.api.search` holds
    the rationale, including why this is registered directly on ``app`` and not as an
    included router. A list route like any other, so ``?format=csv`` comes with it --
    but not through ``reads``, so it keeps its own ``q`` parameter rather than the
    filter vocabulary :func:`_filter_vocabulary` derives for every resource that is."""
    return csv_response(Hit, search(db, q), "search") if format == "csv" else search(db, q)


def _register_routes(app: FastAPI) -> None:
    """The handlers written out longhand in this module, attached to ``app``.

    ``add_api_route`` rather than the ``@app.get``/``@app.post`` decorators these used to
    carry: a decorator runs at import against whichever app is in scope, which is exactly
    the module-scope registration :func:`create_app` exists to end. The handlers keep
    their names -- :func:`driftless.api.secure._leaves` and ``tests/test_secure.py`` walk
    endpoint source and match by name, so a rename here is a silent gate change.
    """
    app.add_exception_handler(IntegrityError, _on_integrity_error)  # type: ignore[arg-type]
    app.add_api_route("/health", health, methods=["GET"])
    app.add_api_route("/health/ready", health_ready, methods=["GET"])
    app.add_api_route("/calendar.ics", calendar_feed, methods=["GET"])
    app.add_api_route("/projects/{project_id}/calendar.ics", project_calendar_feed, methods=["GET"])
    app.add_api_route("/projects/{project_id}/ev-series", project_ev_series, methods=["GET"])
    app.add_api_route("/search/results", search_results, methods=["GET"], response_model=list[Hit])
    for path, handler, out in (
        ("/businesses", create_business, s.BusinessOut),
        ("/portfolios", create_portfolio, s.PortfolioOut),
        ("/programs", create_program, s.ProgramOut),
        ("/projects", create_project, s.ProjectOut),
        ("/workstreams", create_workstream, s.WorkstreamOut),
        ("/tasks", create_task, s.TaskOut),
        ("/status-snapshots", post_status_snapshot, s.StatusSnapshotOut),
        ("/sign-offs", post_sign_off, s.SignOffOut),
        ("/technique-runs", post_technique_run, s.TechniqueRunOut),
    ):
        app.add_api_route(path, handler, methods=["POST"], response_model=out, status_code=201)


def create_app() -> FastAPI:
    """Build the whole API -- routes, pages, versioned twins -- and return it.

    Everything here ran at module scope against a global until now, so importing this
    module WAS the construction and a process could hold exactly one app. The order is
    the order it always was, and two of the steps depend on it: ``mount_web`` must land
    before :func:`driftless.api.versioning.install_versioned_api`, which reads the
    FINISHED table, and ``install_page_errors`` must land before the app is first called,
    because Starlette snapshots the handler table into the middleware stack then.
    """
    app = FastAPI(
        title="driftless",
        version=__version__,
        lifespan=_lifespan,
        dependencies=[Depends(_BEARER_CREDENTIAL)],
    )
    install_request_log(app)  # structured request log; silent until its logger is raised to INFO
    install_metrics(app)  # GET /metrics, gated like every route -- see driftless/api/metrics.py
    install_api_only_openapi(app)  # schema minus HTML pages -- see driftless/api/openapi.py
    install_idempotency(app)  # Idempotency-Key on writes -- see driftless/api/idempotency.py
    _register_routes(app)
    register_resources(app)
    install_page_errors(app)
    mount_web(app)
    # Last, deliberately: this reads the finished route table, so every resource route
    # above (and the page routes just mounted, which it excludes by class) must exist.
    install_versioned_api(app)
    return app


# Module scope, and not an implementation detail: the production entrypoint is
# ``uvicorn driftless.api.secure:secured`` (Dockerfile), and driftless.api.secure imports
# THIS name to wrap it. tests/test_app_factory.py asserts it survives.
app = create_app()
