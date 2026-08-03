"""CRUD over the hierarchy: business -> portfolio -> program -> project -> workstream -> task.

Nothing binds a socket or opens an engine at import time — the session arrives
as a dependency, so a test can hand the app a throwaway database. Reads take no
request body, so one generic pair serves every entity — which is also why every
list endpoint takes ``?format=csv`` for free (driftless/api/export.py). A
create's body type is exactly what FastAPI validates against, so those stay
written out. Updates are
registered generically too — their body types are *generated* patch twins, so
there is nothing to write out and the annotation is attached at registration.
"""

import logging
import os
import sys
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import date
from typing import Annotated, Any, TypeVar

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.interfaces import ONETOMANY

from driftless import __version__
from driftless.api import calendar, schemas as s
from driftless.api.export import Format, csv_response
from driftless.api.logging import install_request_log
from driftless.api.search import Hit, search
from driftless.auth.principal import Principal
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog, set_actor
from driftless.db.config import database_url
from driftless.db.schema_version import EXPECTED_REVISION, SchemaAheadError, schema_is_ahead
from driftless.models import (
    Baseline,
    BaselineLine,
    BudgetLine,
    Business,
    ChangeRequest,
    CostEntry,
    Department,
    Issue,
    Milestone,
    NarrativeArtifact,
    Person,
    Portfolio,
    ProcurementAgreement,
    Program,
    Project,
    QualityMeasurement,
    Risk,
    SignOff,
    Sprint,
    Stakeholder,
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
    this runs when the server starts, so a test importing the app pays nothing.

    It is also the web mount's backstop, for the one import order that cannot mount at
    import (:func:`_web_mid_import`) — the route table is complete before request one."""
    _mount_web()
    refuse_if_schema_ahead()
    yield


app = FastAPI(title="driftless", version=__version__, lifespan=_lifespan)
install_request_log(app)  # structured request log; silent until its logger is raised to INFO

M = TypeVar("M", bound=Base)
Check = Callable[[Session, Any, dict[str, Any]], None]  # a rule run over a pending patch
CreateCheck = Callable[[Session, Any], None]  # a rule run over a create payload
DeleteCheck = Callable[[Session, Any], None]  # a rule run over a row about to be deleted
_factory: sessionmaker[Session] | None = None
_web_mounted = False  # the web mount runs once, from import or from the lifespan
_UNIT_FOR_MODE = {"agile": "points", "predictive": "hours"}  # hybrid takes either
ALLOW_SCHEMA_AHEAD_ENV = "DRIFTLESS_ALLOW_SCHEMA_AHEAD"  # the startup refusal's one override
LIST_LIMIT = 500  # rows a list answers when the caller asks for no window
LIST_LIMIT_MAX = 2000  # the ceiling ``?limit`` cannot be raised past


@contextmanager
def session_scope() -> Iterator[Session]:
    """A short-lived session, building the single factory on first use."""
    global _factory
    if _factory is None:
        url = database_url(default="sqlite:///driftless.db")
        _factory = new_session_factory(new_engine(url))
        # Every write through the API is audited: the flush listener records it
        # on the ChangeLog, so the self-onboarding path can prove each output was
        # produced through the validated boundary and no other.
        register_changelog(_factory)
    with _factory() as db:
        yield db


def _actor(request: Request) -> str | None:
    """The username the gate resolved for this request, or ``None`` for no identity.

    Read off the ASGI scope where :class:`driftless.api.secure.TokenGate` stamped it,
    so the identity is looked up once per request and never a second time here.
    """
    who = (request.scope.get("state") or {}).get("principal")
    return who.username if isinstance(who, Principal) else None


def signer(request: Request, claimed: str) -> str:
    """Who the sign-off ledger records — the resolved principal, never the caller's claim.

    The same rule as the ChangeLog actor above, applied to the one column whose whole
    value is that it names a person: when the gate resolved an identity, that identity
    is what is written and the request's own ``signed_by`` is discarded, exactly as a
    ``StatusSnapshot``'s percent is stamped from calc rather than accepted from the
    request. Otherwise any contributor could append a permanent, un-deletable approval
    in a colleague's name.

    Discarded, not refused: both browser forms post the field on every sign-off, so a
    4xx would break the UI's own write while adding nothing — the 201 body carries the
    name actually stored, so a caller is never told a claim it did not get.

    The claim survives on exactly one path, and deliberately: the shared
    ``DRIFTLESS_API_TOKEN`` bearer resolves no principal (it is the bootstrap credential
    — see :func:`driftless.api.secure._refuses_write`), so an importer or an agent
    recording a decision a named human made offline supplies the name itself. Inventing
    one there would put a name on a row nobody signed; refusing it would delete the only
    honest on-behalf-of write the service has.
    """
    return _actor(request) or claimed


def get_session(request: Request) -> Iterator[Session]:
    """Yield a request-scoped session that credits its writes to the signed-in user.

    The credit is stamped here rather than at each write site, for the same reason
    the ChangeLog listener exists at all: a per-endpoint convention is something a
    future writer forgets, and this is the one dependency every route already takes.

    What is deliberately NOT attributed: a request authorized by the shared
    ``DRIFTLESS_API_TOKEN`` bearer resolves no principal, so its writes stay
    ``actor=None`` — the same as a CLI or migration write. That token is the
    bootstrap credential, and per-user API tokens are a separate, planned unit;
    inventing an actor for it would put a name on a row nobody signed.
    """
    with session_scope() as db:
        set_actor(db, _actor(request))
        yield db


Db = Annotated[Session, Depends(get_session)]


# Fixed wording for a page-surface 409, in the idiom of ``web.errors._MESSAGES``:
# the exception is never rendered, so no constraint name, SQL or row can leak.
_CONFLICT = (
    "That was already recorded",
    "The store already holds an entry for exactly that — most often a weekly status "
    "filed for a date that already has one. Go back to the page: the existing entry "
    "is already on it.",
)


@app.exception_handler(IntegrityError)
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
    byte-for-byte what it was. Imported lazily because ``driftless.web`` imports
    this module.
    """
    from driftless.web import errors as web_errors

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


@app.get("/health")
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


@app.get("/health/ready")
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


def fetch(db: Session, model: type[M], row_id: int) -> M:
    """Load a row or 404 — the alternative is a foreign-key 500 on insert."""
    row = db.get(model, row_id)
    if row is None:
        raise HTTPException(404, f"{model.__name__} {row_id} not found")
    return row


def insert(db: Session, model: type[M], payload: BaseModel, **parents: type[Base]) -> M:
    """Check every named parent exists, then write the row."""
    data = payload.model_dump()
    for field, parent in parents.items():
        if data[field] is not None:
            fetch(db, parent, data[field])
    row = model(**data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _apply(
    db: Session, row: M, payload: BaseModel, check: Check | None = None, **parents: type[Base]
) -> M:
    """Write only the fields the request actually carried.

    ``exclude_unset`` is the whole partial-update contract: an omitted key is
    absent from the dump and never touches the column, while an explicit null
    is present and clears it. Dumping everything would blank each field the
    caller left out.
    """
    data = payload.model_dump(exclude_unset=True)
    # Parents are resolved before the cross-row rules run: a rule that reads the
    # target row would otherwise answer its own 409 for a parent that does not
    # exist at all, hiding the plain 404.
    for field, parent in parents.items():
        if data.get(field) is not None:
            fetch(db, parent, data[field])
    if check is not None:
        check(db, row, data)
    for field, value in data.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


def _delete(db: Session, model: type[M], row_id: int, check: DeleteCheck | None = None) -> None:
    """Refuse to delete a row that still owns children.

    The hierarchy's whole premise is that a parent's rollup covers everything
    under it, so a cascade would silently destroy the numbers a report was
    built from. Refusing is recoverable; a cascade is not. The child sets are
    read off the mapper rather than listed here, so a relationship added later
    is protected without anyone remembering to update this function.
    """
    row = fetch(db, model, row_id)
    if check is not None:
        check(db, row)
    # ``viewonly`` relationships block too, deliberately: a project's baselines,
    # milestones and sprints are readable-only from the project side but still
    # its children, and losing them is exactly the data loss this refuses.
    blocking = [
        rel.key
        for rel in sa_inspect(model).relationships
        if rel.direction is ONETOMANY and getattr(row, rel.key)
    ]
    if blocking:
        raise HTTPException(409, f"{model.__name__} {row_id} still has {', '.join(blocking)}")
    db.delete(row)
    db.commit()


def _windowed(response: Response, total: int, limit: int, offset: int) -> Response:
    """Say which window of which table this answer is — a bound nobody reports is worse
    than none: the caller cannot tell "all the rows" from "the first 500", and totals a
    truncated read. Both encodings carry it, so the CSV is as honest as the JSON."""
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)
    return response


def _reads(path: str, model: type[M], out: Any) -> None:
    def list_rows(
        response: Response,
        db: Db,
        format: Format = "json",
        limit: int = LIST_LIMIT,
        offset: int = 0,
    ) -> Any:
        # ``?format=csv`` is answered at this one registration point rather than
        # by a second route per entity: every list route is created here, so an
        # entity added later is exportable by construction and nobody has to
        # remember. FastAPI hands a Response straight back, response_model and
        # all, so the json branch below is untouched byte for byte.
        #
        # One page of rows, never the whole table, and the window is the SERVER's:
        # a bare GET answers LIST_LIMIT rows and ``?limit`` is clamped to
        # LIST_LIMIT_MAX, so no request loads a commercial store's every row into
        # memory -- and the csv branch, which builds the whole answer as one string
        # before sending a byte, is bounded by exactly the same window. Clamped
        # rather than refused: the caller gets the most the server will serve, plus
        # headers saying what is left, where a 422 is a dead end. Ordered by primary
        # key because an unordered OFFSET is an arbitrary slice per page -- paging
        # would both repeat and skip rows.
        window, start = min(max(limit, 0), LIST_LIMIT_MAX), max(offset, 0)
        total = db.scalar(select(func.count()).select_from(model)) or 0
        page = select(model).order_by(*sa_inspect(model).primary_key).offset(start).limit(window)
        rows = list(db.scalars(page))
        if format == "csv":
            return _windowed(csv_response(out, rows, path.strip("/")), total, window, start)
        _windowed(response, total, window, start)
        return rows

    def get_row(row_id: int, db: Db) -> Any:
        return fetch(db, model, row_id)

    app.add_api_route(path, list_rows, methods=["GET"], response_model=list[out])
    app.add_api_route(f"{path}/{{row_id}}", get_row, methods=["GET"], response_model=out)


def _writes(
    path: str,
    model: type[M],
    out: Any,
    patch: type[BaseModel],
    check: Check | None = None,
    delete_check: DeleteCheck | None = None,
    **parents: type[Base],
) -> None:
    def update_row(row_id: int, payload: BaseModel, db: Db) -> Any:
        return _apply(db, fetch(db, model, row_id), payload, check, **parents)

    def delete_row(row_id: int, db: Db) -> None:
        _delete(db, model, row_id, delete_check)

    update_row.__annotations__["payload"] = patch  # a generated twin has no source annotation
    route = f"{path}/{{row_id}}"
    app.add_api_route(route, update_row, methods=["PATCH"], response_model=out)
    app.add_api_route(route, delete_row, methods=["DELETE"], status_code=204)


def _creates(
    path: str,
    model: type[M],
    payload_type: type[BaseModel],
    out: Any,
    check: CreateCheck | None = None,
    **parents: type[Base],
) -> None:
    """Register a POST that validates named parents exist, then writes the row.

    The body type is attached at registration exactly as ``_writes`` does for
    patches: a create's validation *is* its request schema, so FastAPI needs the
    annotation but there is nothing bespoke to write out per entity.
    """

    def create_row(payload: BaseModel, db: Db) -> Any:
        if check is not None:
            check(db, payload)
        return insert(db, model, payload, **parents)

    create_row.__annotations__["payload"] = payload_type
    app.add_api_route(path, create_row, methods=["POST"], response_model=out, status_code=201)


def _require_matching_unit(db: Session, workstream_id: int, estimate_unit: str) -> None:
    """Reject a unit the project's mode does not use — a rule spanning two rows."""
    project = fetch(db, Workstream, workstream_id).project
    required = _UNIT_FOR_MODE.get(project.delivery_mode)
    if required is not None and estimate_unit != required:
        raise HTTPException(
            422,
            f"a {project.delivery_mode} project estimates in {required}, not {estimate_unit}",
        )


def _task_unit_still_matches(db: Session, row: Task, data: dict[str, Any]) -> None:
    """The same rule, applied to the task as the patch will leave it — not as it is."""
    _require_matching_unit(
        db,
        data.get("workstream_id", row.workstream_id),
        data.get("estimate_unit", row.estimate_unit),
    )


def _task_stays_in_its_project(db: Session, row: Task, data: dict[str, Any]) -> None:
    """A task is refiled between its own project's workstreams, never across projects.

    Within one project the move changes nothing any rollup reads, and it is the
    only correction a misfiled task has once its baseline is approved — the plan
    freeze refuses the line delete, and the delete guard refuses the task. A
    target workstream in another project is refused outright: it would carry the
    task's estimates and baseline lines out of one project's numbers into
    another's, the same hole the line-side rule closes from the other end.
    """
    workstream_id = data.get("workstream_id", row.workstream_id)
    if workstream_id == row.workstream_id:
        return
    home = row.workstream.project_id
    target = fetch(db, Workstream, workstream_id).project_id
    if target != home:
        raise HTTPException(
            409,
            f"Workstream {workstream_id} belongs to project {target}, not project {home}; "
            f"a task moves only between its own project's workstreams",
        )


def _task_patch_stays_valid(db: Session, row: Task, data: dict[str, Any]) -> None:
    """Every cross-row task rule, applied to the task as the patch will leave it."""
    _task_stays_in_its_project(db, row, data)
    _task_unit_still_matches(db, row, data)


def _refuse_stranded_units(db: Session, mode: str, owned: ColumnElement[bool]) -> None:
    """Refuse a move that would leave ``owned`` tasks estimating in a unit ``mode`` never uses.

    A flip that landed would write-lock every mismatched task: the row itself
    violates ``_task_unit_still_matches``, so each later task PATCH answers 422
    until the flip is reverted. Refusing here keeps that state unconstructable.
    """
    required = _UNIT_FOR_MODE.get(mode)
    if required is None:  # hybrid takes either unit
        return
    stranded = db.scalars(
        select(Task.id).where(owned, Task.estimate_unit != required).order_by(Task.id)
    ).all()
    if stranded:
        ids = ", ".join(str(task_id) for task_id in stranded)
        raise HTTPException(
            409,
            f"a {mode} project estimates in {required}; "
            f"{len(stranded)} task(s) ({ids}) would not — move or re-unit them first",
        )


def _project_mode_still_fits_tasks(db: Session, row: Project, data: dict[str, Any]) -> None:
    """The unit rule from the project side: no mode flip over mismatched tasks."""
    mode = data.get("delivery_mode", row.delivery_mode)
    if mode != row.delivery_mode:
        under = select(Workstream.id).where(Workstream.project_id == row.id)
        _refuse_stranded_units(db, mode, Task.workstream_id.in_(under))


def _project_still_consistent(db: Session, row: Project, data: dict[str, Any]) -> None:
    """Every cross-row project rule, applied to the row as the patch will leave it."""
    _project_program_still_home(db, row, data)
    _project_stays_in_its_business(db, row, data)
    _require_department_in_business(
        db,
        data.get("portfolio_id", row.portfolio_id),
        data.get("responsible_department_id", row.responsible_department_id),
    )
    _project_mode_still_fits_tasks(db, row, data)


def _workstream_tasks_still_fit(db: Session, row: Workstream, data: dict[str, Any]) -> None:
    """The unit rule from the workstream side: its tasks must fit the target project's mode."""
    project_id = data.get("project_id", row.project_id)
    if project_id != row.project_id:
        project = fetch(db, Project, project_id)
        _refuse_stranded_units(db, project.delivery_mode, Task.workstream_id == row.id)


def _workstream_tasks_stay_home(db: Session, row: Workstream, data: dict[str, Any]) -> None:
    """A workstream move is a batched task move — refuse it while tasks would follow.

    A task's home project is derived through its workstream, so this move carried
    every task under it across the boundary ``_task_stays_in_its_project`` refuses
    one task at a time — in a single 200 that never touched a task row, and never
    passed the plan freeze, leaving an approved baseline's line planning work that
    now lives elsewhere. Emptied, the move is legitimate and still goes through.
    """
    if data.get("project_id", row.project_id) == row.project_id:
        return
    carried = db.scalars(select(Task.id).where(Task.workstream_id == row.id)).all()
    if carried:
        ids = ", ".join(str(task_id) for task_id in sorted(carried))
        raise HTTPException(
            409,
            f"Workstream {row.id} still has {len(carried)} task(s) ({ids}); "
            f"a task does not change project by patch — move them first",
        )


def _workstream_patch_stays_valid(db: Session, row: Workstream, data: dict[str, Any]) -> None:
    """Every workstream patch rule: no task crosses a project, and units still fit."""
    _workstream_tasks_stay_home(db, row, data)
    _workstream_tasks_still_fit(db, row, data)


def _require_baseline_open(db: Session, baseline_id: int) -> None:
    """An approved baseline is the plan of record — writes are refused, not merged.

    ``models.delivery`` holds the approval fact and leaves refusal to this layer
    deliberately. The check reads the row as it stands, so the approval PATCH
    itself — stamping ``approved_at`` onto a draft — is the one write that
    passes, and every write after it answers 409.

    Approval is read from *either* signal. Both write paths now hold the two in
    step (``schemas.approval_is_atomic``), so they cannot disagree; keying on
    either is defence in depth, so a row that somehow carries only one — a legacy
    row, a future path that sets the status alone — is still the plan of record
    and still frozen, rather than silently editable and deletable.
    """
    baseline = fetch(db, Baseline, baseline_id)
    if baseline.status == "approved" or baseline.approved_at is not None:
        raise HTTPException(
            409,
            f"Baseline {baseline_id} is approved (at {baseline.approved_at}); "
            f"a plan change is a new version",
        )


def _baseline_still_open(db: Session, row: Baseline, data: dict[str, Any]) -> None:
    _require_baseline_open(db, row.id)


def _baseline_approval_stays_atomic(db: Session, row: Baseline, data: dict[str, Any]) -> None:
    """``status == "approved"`` and ``approved_at`` move together or not at all.

    The rule itself is ``schemas.approval_is_atomic`` — stated once, so the two
    write paths cannot drift apart. A create settles it in the request type; a
    patch carries only some of the fields, so it is asked here of the row as the
    patch will leave it.
    """
    if not s.approval_is_atomic(
        data.get("status", row.status), data.get("approved_at", row.approved_at)
    ):
        raise HTTPException(
            422, "a baseline's status 'approved' and approved_at must be set together"
        )


def _baseline_patch_stays_valid(db: Session, row: Baseline, data: dict[str, Any]) -> None:
    """Every baseline patch rule: an approved plan is frozen, and approval is atomic."""
    _baseline_still_open(db, row, data)
    _baseline_approval_stays_atomic(db, row, data)


def _baseline_delete_only_while_open(db: Session, row: Baseline) -> None:
    """Deleting an approved baseline vaporizes the plan of record — refuse it.

    Draining a baseline's lines then deleting it would erase the numbers a report
    was built from with no child left for the generic delete guard to catch. This
    mirrors ``_line_leaves_baseline_open`` on the line side.
    """
    _require_baseline_open(db, row.id)


def _require_line_inside_project(db: Session, baseline_id: int, task_id: int) -> None:
    """A line may only plan a task of its baseline's own project — a rule spanning rows.

    Without it one project's EV silently borrows another's task, and both
    projects report numbers built from work only one of them owns.
    """
    baseline = fetch(db, Baseline, baseline_id)
    home = fetch(db, Task, task_id).workstream.project_id
    if home != baseline.project_id:
        raise HTTPException(
            422,
            f"Task {task_id} belongs to project {home}, "
            f"not project {baseline.project_id} that Baseline {baseline_id} plans",
        )


def _line_lands_open_and_inside(db: Session, payload: Any) -> None:
    _require_baseline_open(db, payload.baseline_id)
    _require_line_inside_project(db, payload.baseline_id, payload.task_id)


def _line_still_open_and_inside(db: Session, row: BaselineLine, data: dict[str, Any]) -> None:
    _require_baseline_open(db, row.baseline_id)
    baseline_id = data.get("baseline_id", row.baseline_id)
    if baseline_id != row.baseline_id:
        _require_baseline_open(db, baseline_id)  # nor may a line slide into an approved plan
    _require_line_inside_project(db, baseline_id, data.get("task_id", row.task_id))


def _line_leaves_baseline_open(db: Session, row: BaselineLine) -> None:
    _require_baseline_open(db, row.baseline_id)


def _require_program_in_portfolio(db: Session, portfolio_id: int, program_id: int | None) -> None:
    """Reject a program from another portfolio — a rule spanning two rows.

    Without it the row would land but vanish from every rollup surface: the
    grouped walk only yields a portfolio's own programs, so a project filed
    under a foreign program has no bucket to appear in.
    """
    if program_id is None:
        return
    program = fetch(db, Program, program_id)
    if program.portfolio_id != portfolio_id:
        raise HTTPException(
            422,
            f"Program {program_id} lives in portfolio {program.portfolio_id}, "
            f"not portfolio {portfolio_id}",
        )


def _project_program_still_home(db: Session, row: Project, data: dict[str, Any]) -> None:
    """The same rule, applied to the project as the patch will leave it — not as it is."""
    _require_program_in_portfolio(
        db,
        data.get("portfolio_id", row.portfolio_id),
        data.get("program_id", row.program_id),
    )


def _program_projects_still_home(db: Session, row: Program, data: dict[str, Any]) -> None:
    """Refuse to move a program out from under its projects — a rule spanning rows.

    Changing ``portfolio_id`` while projects reference the program creates
    exactly the stray rows the grouped rollup walk fails loudly on, taking the
    dashboard down with it. Delete refuses to orphan children; so does a move.
    """
    if data.get("portfolio_id", row.portfolio_id) == row.portfolio_id:
        return
    stranded = db.scalars(
        select(Project.id).where(Project.program_id == row.id).order_by(Project.id)
    ).all()
    if stranded:
        ids = ", ".join(str(project_id) for project_id in stranded)
        raise HTTPException(
            409,
            f"Program {row.id} still has {len(stranded)} project(s) ({ids}); move them first",
        )


def _refuse_move_with_children(label: str, row_id: int, held: dict[str, bool]) -> None:
    """Refuse a business move that would drag rows along, naming what holds it.

    Reads like the delete guard on purpose — "still has programs" — because it
    refuses the same loss for the same reason: everything under the row would
    change business in one call, and both businesses' rollups would silently
    restate. Emptied, the move is legitimate and goes through.
    """
    kinds = [kind for kind, present in held.items() if present]
    if kinds:
        raise HTTPException(409, f"{label} {row_id} still has {', '.join(kinds)}; move them first")


def _portfolio_children_stay_home(db: Session, row: Portfolio, data: dict[str, Any]) -> None:
    """A portfolio carries every program, project and record under it — no silent move."""
    if data.get("business_id", row.business_id) != row.business_id:
        _refuse_move_with_children(
            "Portfolio", row.id, {"programs": bool(row.programs), "projects": bool(row.projects)}
        )


def _department_children_stay_home(db: Session, row: Department, data: dict[str, Any]) -> None:
    """A department's people and the projects it answers for belong to its business."""
    if data.get("business_id", row.business_id) != row.business_id:
        responsible = db.scalar(
            select(Project.id).where(Project.responsible_department_id == row.id)
        )
        _refuse_move_with_children(
            "Department",
            row.id,
            {"people": bool(row.people), "responsible projects": responsible is not None},
        )


def _business_of(db: Session, portfolio_id: int) -> int:
    return fetch(db, Portfolio, portfolio_id).business_id


def _project_stays_in_its_business(db: Session, row: Project, data: dict[str, Any]) -> None:
    """A patch may re-file a project inside its business, never across businesses.

    ``_require_program_in_portfolio`` returns early for a programless project and
    ``program_id`` is nullable by design, so that rule alone left the common case
    free to land under any portfolio anywhere — taking its cost entries and every
    record under it out of the business that owns the work.
    """
    portfolio_id = data.get("portfolio_id", row.portfolio_id)
    if portfolio_id == row.portfolio_id:
        return
    home, target = _business_of(db, row.portfolio_id), _business_of(db, portfolio_id)
    if target != home:
        raise HTTPException(
            409,
            f"Portfolio {portfolio_id} is in business {target}, not business {home}; "
            f"Project {row.id} does not change business by patch",
        )


def _require_department_in_business(
    db: Session, portfolio_id: int, department_id: int | None
) -> None:
    """Reject a responsible department from another business — a rule spanning rows.

    The Department report rolls a business's projects up by the department
    accountable for each, so a foreign department files a project's numbers
    under a business that does not own the work.
    """
    if department_id is None:
        return
    business_id = _business_of(db, portfolio_id)
    department = fetch(db, Department, department_id)
    if department.business_id != business_id:
        raise HTTPException(
            409,
            f"Department {department_id} is in business {department.business_id}, "
            f"not business {business_id} that this project's portfolio belongs to",
        )


def _link_stays_in_project(
    model: type[Risk] | type[Baseline], field: str
) -> tuple[CreateCheck, Check]:
    """Build the create *and* patch rules that keep a secondary link inside its project.

    ``Issue.risk_id`` and ``ChangeRequest.resulting_baseline_id`` are links rather
    than parents, so the patch twin keeps them — and neither write path scoped
    them at all. Every reader takes the link as same-project by construction: the
    risk register reads a risk's issues as its own lineage, and the scope report
    reads a change request's baseline as the plan version it produced. Both rules
    come from one call, so a registration cannot wire the create and forget the
    patch.
    """

    def require(db: Session, link_id: int | None, project_id: int) -> None:
        if link_id is None:
            return
        home = fetch(db, model, link_id).project_id
        if home != project_id:
            raise HTTPException(
                409,
                f"{model.__name__} {link_id} belongs to project {home}, not project "
                f"{project_id}; {field} links only inside its own project",
            )

    def on_create(db: Session, payload: Any) -> None:
        require(db, getattr(payload, field), payload.project_id)

    def on_patch(db: Session, row: Any, data: dict[str, Any]) -> None:
        require(db, data.get(field, getattr(row, field)), row.project_id)

    return on_create, on_patch


def _sprint_window_still_ordered(db: Session, row: Sprint, data: dict[str, Any]) -> None:
    """The ``SprintIn`` date-order rule, applied to the sprint as the patch will leave it."""
    start = data.get("start_date", row.start_date)
    end = data.get("end_date", row.end_date)
    if end <= start:
        raise HTTPException(422, f"end_date {end} must be strictly after start_date {start}")


@app.post("/businesses", response_model=s.BusinessOut, status_code=201)
def create_business(payload: s.BusinessIn, db: Db) -> Business:
    return insert(db, Business, payload)


@app.post("/portfolios", response_model=s.PortfolioOut, status_code=201)
def create_portfolio(payload: s.PortfolioIn, db: Db) -> Portfolio:
    return insert(db, Portfolio, payload, business_id=Business)


@app.post("/programs", response_model=s.ProgramOut, status_code=201)
def create_program(payload: s.ProgramIn, db: Db) -> Program:
    return insert(db, Program, payload, portfolio_id=Portfolio)


@app.post("/projects", response_model=s.ProjectOut, status_code=201)
def create_project(payload: s.ProjectIn, db: Db) -> Project:
    _require_program_in_portfolio(db, payload.portfolio_id, payload.program_id)
    _require_department_in_business(db, payload.portfolio_id, payload.responsible_department_id)
    return insert(
        db,
        Project,
        payload,
        portfolio_id=Portfolio,
        program_id=Program,
        responsible_department_id=Department,
    )


@app.post("/workstreams", response_model=s.WorkstreamOut, status_code=201)
def create_workstream(payload: s.WorkstreamIn, db: Db) -> Workstream:
    return insert(db, Workstream, payload, project_id=Project)


@app.post("/tasks", response_model=s.TaskOut, status_code=201)
def create_task(payload: s.TaskIn, db: Db) -> Task:
    _require_matching_unit(db, payload.workstream_id, payload.estimate_unit)
    return insert(db, Task, payload, assignee_id=Person)


def stamped_percent(db: Session, project: Project, as_of: date) -> int:
    """The project's percent complete at ``as_of``, computed from calc, never typed.

    Reads through :func:`driftless.assess.adapters.project_snapshot` — the
    session-holding EVM adapter whose ChangeLog replay dates each progress
    reading — so the number stamped onto a weekly snapshot is the figure that
    was true at the snapshot's OWN date. ``gather.project_evm`` holds no session,
    so it reads ``Task.percent_complete``, an undated *current* number: a
    snapshot backdated to February recorded today's completion, and the
    append-only series (no PATCH or DELETE exists for it) made that wrong figure
    permanent, plotted forever by the trend chart. Imported lazily because
    ``assess`` sits below the API in the import order.
    """
    from driftless.assess import adapters

    snap = adapters.project_snapshot(db, project, as_of)
    return round(snap.ev / snap.bac * 100) if snap.bac else 0


@app.post("/status-snapshots", response_model=s.StatusSnapshotOut, status_code=201)
def create_status_snapshot(payload: s.StatusSnapshotIn, db: Db) -> StatusSnapshot:
    """Create a weekly snapshot, stamping percent complete from calc.

    The client sends the RAG and note it authored; the completion figure is
    computed here from the tasks under the project — never accepted from the
    request — so the series can never hold a hand-typed number that disagrees
    with the work actually done.
    """
    project = fetch(db, Project, payload.project_id)
    row = StatusSnapshot(
        project_id=project.id,
        taken_on=payload.taken_on,
        rag_status=payload.rag_status,
        note=payload.note,
        percent_complete=stamped_percent(db, project, payload.taken_on),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def stamped_signal(db: Session, payload: s.SignOffIn) -> float | None:
    """The score a sign-off records, computed from the store and never accepted from it.

    ``signal`` is the whole re-arm mechanism — :func:`driftless.assess.engine.is_suppressed`
    keeps a signed-off threat hidden only while its live score stays no worse than this
    number — so a request-supplied one muted a threat permanently on an append-only row.
    The assessment engine is re-run here for the named project at the sign-off's own
    as-of and the score of the threat ``subject_ref`` names is taken from it (never
    rescored locally). The ref carries its own project, so a mismatched ``project_id``
    matches nothing rather than some other threat's score.

    ``None`` — which never suppresses — whenever there is no such score to record: a
    process decision, a threat that is not live at that as-of, or a sign-off naming no
    project or no as-of date, there being no clock to fall back on by design. Imported
    lazily because ``assess`` sits below the API in the import order, as ``gather`` does.
    """
    from driftless.assess import engine as assess

    if payload.subject_kind != "threat" or payload.project_id is None or payload.as_of is None:
        return None
    scores = {
        threat.id: threat.score
        for assessment in assess.assess_project(
            db, fetch(db, Project, payload.project_id), payload.as_of
        )
        for threat in assessment.threats
    }
    return scores.get(payload.subject_ref)


@app.post("/sign-offs", response_model=s.SignOffOut, status_code=201)
def create_sign_off(request: Request, payload: s.SignOffIn, db: Db) -> SignOff:
    """Append a decision to the sign-off ledger.

    Append-only: there is deliberately no PATCH or DELETE for sign-offs — a
    reversal is a new row with the opposite decision, so the ledger is the whole
    history and the current position is its latest entry for a subject. Which is
    exactly why the signer is :func:`signer`'s to decide and not the request's, and
    the suppression signal :func:`stamped_signal`'s: a forged name or a forged
    threshold here could never be taken back.

    Both write paths land here — ``driftless.web.pages.sign_off`` calls this route
    rather than assembling its own row, so the browser form cannot hold a weaker
    guarantee than the JSON one.
    """
    if payload.project_id is not None:
        fetch(db, Project, payload.project_id)
    row = SignOff(
        **{
            **payload.model_dump(),
            "signed_by": signer(request, payload.signed_by),
            "signal": stamped_signal(db, payload),
        }
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


_reads("/businesses", Business, s.BusinessOut)
_reads("/portfolios", Portfolio, s.PortfolioOut)
_reads("/programs", Program, s.ProgramOut)
_reads("/projects", Project, s.ProjectOut)
_reads("/workstreams", Workstream, s.WorkstreamOut)
_reads("/tasks", Task, s.TaskOut)

_writes("/businesses", Business, s.BusinessOut, s.BusinessPatch)
_writes(
    "/portfolios",
    Portfolio,
    s.PortfolioOut,
    s.PortfolioPatch,
    _portfolio_children_stay_home,
    business_id=Business,
)
_writes(
    "/programs",
    Program,
    s.ProgramOut,
    s.ProgramPatch,
    _program_projects_still_home,
    portfolio_id=Portfolio,
)
_writes(
    "/projects",
    Project,
    s.ProjectOut,
    s.ProjectPatch,
    _project_still_consistent,
    portfolio_id=Portfolio,
    program_id=Program,
    responsible_department_id=Department,
)
_writes(
    "/workstreams",
    Workstream,
    s.WorkstreamOut,
    s.WorkstreamPatch,
    _workstream_patch_stays_valid,
    project_id=Project,
)
_writes("/tasks", Task, s.TaskOut, s.TaskPatch, _task_patch_stays_valid, assignee_id=Person)

# ---- org ------------------------------------------------------------------------
_creates("/departments", Department, s.DepartmentIn, s.DepartmentOut, business_id=Business)
_reads("/departments", Department, s.DepartmentOut)
_writes(
    "/departments",
    Department,
    s.DepartmentOut,
    s.DepartmentPatch,
    _department_children_stay_home,
    business_id=Business,
)

_creates("/people", Person, s.PersonIn, s.PersonOut, department_id=Department)
_reads("/people", Person, s.PersonOut)
_writes("/people", Person, s.PersonOut, s.PersonPatch, department_id=Department)

# ---- delivery -------------------------------------------------------------------
# No create check: ``BaselineIn`` itself refuses a half-approved body, so this
# registration cannot forget the rule the way a ``check=`` argument can be.
_creates("/baselines", Baseline, s.BaselineIn, s.BaselineOut, project_id=Project)
_reads("/baselines", Baseline, s.BaselineOut)
_writes(
    "/baselines",
    Baseline,
    s.BaselineOut,
    s.BaselinePatch,
    _baseline_patch_stays_valid,
    delete_check=_baseline_delete_only_while_open,
    project_id=Project,
)

_creates(
    "/baseline-lines",
    BaselineLine,
    s.BaselineLineIn,
    s.BaselineLineOut,
    _line_lands_open_and_inside,
    baseline_id=Baseline,
    task_id=Task,
)
_reads("/baseline-lines", BaselineLine, s.BaselineLineOut)
_writes(
    "/baseline-lines",
    BaselineLine,
    s.BaselineLineOut,
    s.BaselineLinePatch,
    _line_still_open_and_inside,
    delete_check=_line_leaves_baseline_open,
    baseline_id=Baseline,
    task_id=Task,
)

_creates("/milestones", Milestone, s.MilestoneIn, s.MilestoneOut, project_id=Project)
_reads("/milestones", Milestone, s.MilestoneOut)
_writes("/milestones", Milestone, s.MilestoneOut, s.MilestonePatch, project_id=Project)

_creates("/sprints", Sprint, s.SprintIn, s.SprintOut, project_id=Project)
_reads("/sprints", Sprint, s.SprintOut)
_writes(
    "/sprints", Sprint, s.SprintOut, s.SprintPatch, _sprint_window_still_ordered, project_id=Project
)

# ---- RAID and cost --------------------------------------------------------------
_creates("/risks", Risk, s.RiskIn, s.RiskOut, project_id=Project)
_reads("/risks", Risk, s.RiskOut)
_writes("/risks", Risk, s.RiskOut, s.RiskPatch, project_id=Project)

_risk_lands, _risk_stays = _link_stays_in_project(Risk, "risk_id")
_creates("/issues", Issue, s.IssueIn, s.IssueOut, _risk_lands, project_id=Project, risk_id=Risk)
_reads("/issues", Issue, s.IssueOut)
_writes("/issues", Issue, s.IssueOut, s.IssuePatch, _risk_stays, project_id=Project, risk_id=Risk)

_plan_lands, _plan_stays = _link_stays_in_project(Baseline, "resulting_baseline_id")
_creates(
    "/change-requests",
    ChangeRequest,
    s.ChangeRequestIn,
    s.ChangeRequestOut,
    _plan_lands,
    project_id=Project,
    resulting_baseline_id=Baseline,
)
_reads("/change-requests", ChangeRequest, s.ChangeRequestOut)
_writes(
    "/change-requests",
    ChangeRequest,
    s.ChangeRequestOut,
    s.ChangeRequestPatch,
    _plan_stays,
    project_id=Project,
    resulting_baseline_id=Baseline,
)

_creates("/budget-lines", BudgetLine, s.BudgetLineIn, s.BudgetLineOut, project_id=Project)
_reads("/budget-lines", BudgetLine, s.BudgetLineOut)
_writes("/budget-lines", BudgetLine, s.BudgetLineOut, s.BudgetLinePatch, project_id=Project)

_creates("/cost-entries", CostEntry, s.CostEntryIn, s.CostEntryOut, project_id=Project)
_reads("/cost-entries", CostEntry, s.CostEntryOut)
_writes("/cost-entries", CostEntry, s.CostEntryOut, s.CostEntryPatch, project_id=Project)

_creates("/stakeholders", Stakeholder, s.StakeholderIn, s.StakeholderOut, project_id=Project)
_reads("/stakeholders", Stakeholder, s.StakeholderOut)
_writes("/stakeholders", Stakeholder, s.StakeholderOut, s.StakeholderPatch, project_id=Project)

# StatusSnapshot: bespoke create (stamps percent) above; the patch touches only
# the human-authored RAG and note, and delete is the generic guarded one.
_reads("/status-snapshots", StatusSnapshot, s.StatusSnapshotOut)
_writes("/status-snapshots", StatusSnapshot, s.StatusSnapshotOut, s.StatusSnapshotPatch)

# ---- narrative / quality / procurement ------------------------------------------
_creates(
    "/narrative-artifacts",
    NarrativeArtifact,
    s.NarrativeArtifactIn,
    s.NarrativeArtifactOut,
    project_id=Project,
)
_reads("/narrative-artifacts", NarrativeArtifact, s.NarrativeArtifactOut)
_writes(
    "/narrative-artifacts",
    NarrativeArtifact,
    s.NarrativeArtifactOut,
    s.NarrativeArtifactPatch,
    project_id=Project,
)

_creates(
    "/quality-measurements",
    QualityMeasurement,
    s.QualityMeasurementIn,
    s.QualityMeasurementOut,
    project_id=Project,
)
_reads("/quality-measurements", QualityMeasurement, s.QualityMeasurementOut)
_writes(
    "/quality-measurements",
    QualityMeasurement,
    s.QualityMeasurementOut,
    s.QualityMeasurementPatch,
    project_id=Project,
)

_creates(
    "/procurement-agreements",
    ProcurementAgreement,
    s.ProcurementAgreementIn,
    s.ProcurementAgreementOut,
    project_id=Project,
)
_reads("/procurement-agreements", ProcurementAgreement, s.ProcurementAgreementOut)
_writes(
    "/procurement-agreements",
    ProcurementAgreement,
    s.ProcurementAgreementOut,
    s.ProcurementAgreementPatch,
    project_id=Project,
)

# SignOff: append-only — bespoke create above, reads only, no patch or delete.
_reads("/sign-offs", SignOff, s.SignOffOut)


@app.get("/calendar.ics")
def calendar_feed(db: Db) -> Response:
    """Every dated record in the store as a subscribable iCalendar feed —
    :mod:`driftless.api.calendar` holds the decisions. Registered directly on ``app`` for
    the reason ``/search/results`` is: an included router's routes are walked as *pages*,
    and ``text/calendar`` is not HTML. It answers a ``Response``, so it has no list
    response model and stays outside the both-formats export walk — a calendar has one
    encoding, and ``?format=csv`` on it would mean nothing."""
    return calendar.feed(db, "driftless")


@app.get("/projects/{project_id}/calendar.ics")
def project_calendar_feed(project_id: int, db: Db) -> Response:
    """One project's dates, at an address that means that project for good."""
    return calendar.feed(db, fetch(db, Project, project_id).name, project_id)


@app.get("/search/results", response_model=list[Hit])
def search_results(db: Db, q: str = "", format: Format = "json") -> Any:
    """Cross-entity search for scripts and agents — :mod:`driftless.api.search` holds
    the rationale, including why this is registered directly on ``app`` and not as an
    included router. A list route like any other, so ``?format=csv`` comes with it."""
    return csv_response(Hit, search(db, q), "search") if format == "csv" else search(db, q)


def _web_mid_import() -> bool:
    """Whether a ``driftless.web`` module is *itself* still executing its body — true
    in one situation only: this module is being imported BY a web submodule (they all
    import helpers from here), so that submodule has not defined its router factory yet
    and :func:`_mount_web` would ask for a name that does not exist. That was the
    circular ``ImportError`` on which ``import driftless.web.pages`` died in a fresh
    process for eleven of the fourteen submodules, the suite staying green only because
    isort sorts ``driftless.api`` above ``driftless.web``. Read off each module's own
    load state, so it holds at any depth, from any importer."""
    return any(
        name.startswith("driftless.web")
        and getattr(getattr(module, "__spec__", None), "_initializing", False)
        for name, module in list(sys.modules.items())
    )


def _mount_web() -> None:
    """Serve the dashboard at ``/`` on the app the server actually runs.

    Runs at most once, from whichever trigger gets there first — module import below, or
    the lifespan when import had to stand down (:func:`_web_mid_import`); a router
    included twice would duplicate every page route.

    ``date.today`` is passed uncalled: the default as-of is resolved per
    request, never at import. An import-time date would freeze at process
    start, and reading the clock inside calc would break the byte-identical
    regeneration every report depends on — the date stays an explicit input.

    Imported here rather than at the top of the file because ``driftless.web``
    imports ``get_session`` from this module.
    """
    global _web_mounted
    if _web_mounted:
        return
    _web_mounted = True
    from fastapi.staticfiles import StaticFiles

    from driftless.web import create_pages_router, create_router, static_dir
    from driftless.web import create_departments_router
    from driftless.web.board import create_board_router
    from driftless.web.business_map import create_business_map_router
    from driftless.web.drills import create_drills_router
    from driftless.web.gantt import create_gantt_router
    from driftless.web.heatmap import create_heatmap_router
    from driftless.web.login import create_login_router
    from driftless.web.project_hub import create_project_hub_router
    from driftless.web.search import create_search_router

    app.include_router(create_project_hub_router(date.today))
    app.include_router(create_gantt_router(date.today))
    app.include_router(create_board_router())  # no as-of either: a task carries no date
    app.include_router(create_search_router())  # no as-of: nothing it renders is dated
    app.include_router(create_router(date.today))
    app.include_router(create_pages_router(date.today))
    app.include_router(create_departments_router(date.today))
    app.include_router(create_heatmap_router(date.today))
    app.include_router(create_drills_router(date.today))
    app.include_router(create_business_map_router(date.today))
    app.include_router(create_login_router())  # sign-in only: it protects nothing
    app.mount("/static", StaticFiles(directory=static_dir()), name="static")


def _install_page_errors() -> None:
    """Designed HTML 404/500 pages, keyed on the page routes themselves, so every JSON
    API error body stays as it was. Registered from module import unconditionally rather
    than from :func:`_mount_web`, because Starlette snapshots the handler table into the
    middleware stack the first time the app is called — BEFORE lifespan startup, so a
    handler added there is never reached and a mistyped page URL would answer JSON. Safe
    in any order: ``driftless.web.errors`` imports nothing from this module."""
    from driftless.web.errors import install_page_errors

    install_page_errors(app)


# Mounted at import in every ordinary order, because the route table is read long
# before any lifespan runs: the credential gate compiles its page patterns as it wraps
# the app, and the snapshot tool walks the routes off a bare import.
_install_page_errors()
if not _web_mid_import():
    _mount_web()
