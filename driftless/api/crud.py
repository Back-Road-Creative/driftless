"""The generic CRUD machinery: how ~30 resources get their routes from one place.

``reads``, ``writes`` and ``creates`` register a resource's list/detail, patch/delete
and create routes onto an app they are handed, deriving everything they need -- the filter
vocabulary, the cursor column, a delete's blocking children -- by reflecting over the
model's mapper rather than from a hand-written table per resource. The helpers below them
window a list, refuse a stale write against a caller-supplied revision, and turn a
mapper's relationships into the set of children that block a delete.

None of this knows which resources exist; :mod:`driftless.api.resources` decides that.
It lived in :mod:`driftless.api.app` only because everything did.

:func:`reads`, :func:`writes` and :func:`creates` carry public names because a second
module calls them, which is the rule ``tests/test_package.py`` enforces: a leading
underscore means "mine", so a helper two modules need is public API. Everything below
them stays private -- nothing outside this module calls it.
"""

from __future__ import annotations

import inspect
from datetime import date
from typing import Annotated, Any, TypeVar

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel
from sqlalchemy import Date, DateTime, ColumnElement, func, inspect as sa_inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.interfaces import ONETOMANY

from driftless.api.deps import Db
from driftless.api.export import Format, csv_response
from driftless.api.records import fetch, insert
from driftless.api.rules import Check, CreateCheck, DeleteCheck
from driftless.db import Base
from driftless.services.concurrency import check_revision


M = TypeVar("M", bound=Base)
LIST_LIMIT = 500  # rows a list answers when the caller asks for no window
LIST_LIMIT_MAX = 2000  # the ceiling ``?limit`` cannot be raised past
_EQUALITY_FILTER_COLUMNS = (
    "status",
    "rag_status",
    "record_kind",
    "record_id",
)  # literal column names, not a vocabulary check
_Filter = tuple[str, Any, type, str]  # (query name, column, python type, comparison)


def _stated_revision(request: Request) -> int | None:
    """The client's ``If-Match`` precondition, or ``None`` if the header was omitted.

    ``None`` is not "revision none" -- it is "no precondition stated", and
    :func:`_apply`/:func:`_delete` treat it as permission to write unconditionally,
    exactly as they did before this precondition existed (see their docstrings for
    why that is the deliberate choice for an omitted header, not an oversight).
    Quoting is accepted but not required: a strict HTTP client sends an ETag-style
    ``If-Match: "3"``, and this store's revision is a bare integer, so both read the
    same. A header that is present but not an integer is a client error, not a
    stale write -- refused with 400 rather than folded into the 409 a real
    mismatch answers.
    """
    header = request.headers.get("if-match")
    if header is None:
        return None
    try:
        return int(header.strip().strip('"'))
    except ValueError as exc:
        raise HTTPException(400, "If-Match must carry an integer row revision") from exc


def _apply(
    db: Session,
    row: M,
    payload: BaseModel,
    check: Check | None = None,
    stated_revision: int | None = None,
    **parents: type[Base],
) -> M:
    """Write only the fields the request actually carried.

    ``exclude_unset`` is the whole partial-update contract: an omitted key is
    absent from the dump and never touches the column, while an explicit null
    is present and clears it. Dumping everything would blank each field the
    caller left out.

    ``stated_revision`` is the caller's ``If-Match`` precondition
    (:func:`_stated_revision`); :func:`~driftless.services.concurrency.check_revision` refuses a stale one before
    anything else runs. A write that passes bumps ``row_revision`` itself, so the
    next precondition a caller states has to name what this write just produced.
    """
    check_revision(row, stated_revision)
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
    setattr(row, "row_revision", getattr(row, "row_revision") + 1)
    db.commit()
    db.refresh(row)
    return row


def _delete(
    db: Session,
    model: type[M],
    row_id: int,
    check: DeleteCheck | None = None,
    stated_revision: int | None = None,
) -> None:
    """Refuse to delete a row that still owns children.

    The hierarchy's whole premise is that a parent's rollup covers everything
    under it, so a cascade would silently destroy the numbers a report was
    built from. Refusing is recoverable; a cascade is not. The child sets are
    read off the mapper rather than listed here, so a relationship added later
    is protected without anyone remembering to update this function.

    ``stated_revision`` is the same ``If-Match`` precondition :func:`_apply`
    checks, refused the same way (:func:`~driftless.services.concurrency.check_revision`) and for the same
    reason: a delete is as destructive a stale write as a patch, and a client
    racing another editor deserves the same chance to re-read and retry before
    the row it meant to remove is gone rather than after.
    """
    row = fetch(db, model, row_id)
    check_revision(row, stated_revision)
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


def _windowed(
    response: Response, total: int, limit: int, offset: int, next_cursor: int | None = None
) -> Response:
    """Say which window of which table this answer is — a bound nobody reports is worse
    than none: the caller cannot tell "all the rows" from "the first 500", and totals a
    truncated read. Both encodings carry it, so the CSV is as honest as the JSON.

    ``X-Next-Cursor`` appears only when a further row actually exists, so its ABSENCE is
    the end-of-collection signal a client can loop on."""
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)
    if next_cursor is not None:
        response.headers["X-Next-Cursor"] = str(next_cursor)
    return response


def _filter_vocabulary(model: type[M]) -> list[_Filter]:
    """Every filter ``list_rows`` accepts for ``model``, read off its mapper once per
    registration -- the same "read it off the mapper" rule that already picks a list
    route's primary key (below) and a delete's blocking children (:func:`_delete`), so
    a resource added later is filterable with no edit here. A foreign key column scopes
    to its parent id; a ``status``/``rag_status`` column filters by equality.

    A ``Date`` column gets an inclusive ``_from``/``_to`` pair. A ``DateTime`` column
    deliberately gets NOTHING, and the line is the column type rather than a hand-picked
    list: every ``DateTime`` in the schema is a system-time stamp (``created_at``,
    ``signed_at``, ``approved_at``, ``revoked_at``, ``expires_at``, ``changed_at``), and
    ``docs/temporal-model.md`` already classes those as sync-cursor territory rather than
    something an as-of question filters on. Offering them here would also hand a caller a
    silent off-by-one: a ``date`` bound compares against midnight, so ``_to=2026-01-10``
    would drop everything stamped later that same day. Nothing derives ``changed_since``
    either -- the append-only ``ChangeLog`` that carries one IS the sync cursor.
    """
    vocabulary: list[_Filter] = []
    for column in sa_inspect(model).columns:
        if column.foreign_keys:
            vocabulary.append((column.key, column, int, "eq"))
        elif column.key in _EQUALITY_FILTER_COLUMNS:
            vocabulary.append((column.key, column, str, "eq"))
        elif isinstance(column.type, Date) and not isinstance(column.type, DateTime):
            vocabulary.append((f"{column.key}_from", column, date, "ge"))
            vocabulary.append((f"{column.key}_to", column, date, "le"))
    return vocabulary


def _query_parameter(name: str, annotation: type) -> inspect.Parameter:
    return inspect.Parameter(
        name, inspect.Parameter.KEYWORD_ONLY, default=Query(None), annotation=annotation | None
    )


def _filter_conditions(
    vocabulary: list[_Filter], filters: dict[str, Any]
) -> list[ColumnElement[bool]]:
    # Both bounds are INCLUSIVE, which is the reading a date range gets asked for -- "issues
    # raised 1st to 31st" means both ends. An exclusive upper bound would also be the one a
    # caller is least likely to notice: it silently drops the last day rather than erroring.
    comparisons = {"ge": lambda c, v: c >= v, "le": lambda c, v: c <= v, "eq": lambda c, v: c == v}
    return [
        comparisons[comparison](column, value)
        for name, column, _annotation, comparison in vocabulary
        if (value := filters.get(name)) is not None
    ]


def reads(app: FastAPI, path: str, model: type[M], out: Any) -> None:
    tag = path.strip("/")  # the one place a resource's OpenAPI tag is decided, for all of them
    vocabulary = _filter_vocabulary(model)
    # The column a cursor compares against, and the ORM attribute holding it. Read once per
    # registration off the mapper, the same way the filter vocabulary and a delete's blocking
    # children are -- so "the rows after the one you saw" is a single comparison on the key a
    # list is ALREADY ordered by, and no resource carries a hand-written cursor column. The
    # attribute name comes from the mapper rather than the column, because the two are only
    # equal by convention and it is the attribute a row is actually read off.
    key = sa_inspect(model).primary_key[0]
    key_attribute = sa_inspect(model).get_property_by_column(key).key
    # Filled from the REGISTERED route below, never listed here: a hand-written set is a
    # second copy of what this route accepts, and the copy that goes stale refuses a
    # parameter the route really does take. Read off FastAPI's own dependant, it cannot
    # disagree with the route -- a parameter added to ``list_rows`` is accepted the moment
    # it exists, and one that is removed stops being accepted, with no edit here.
    accepted: set[str] = set()

    def list_rows(
        request: Request,
        response: Response,
        db: Db,
        format: Format = "json",
        limit: Annotated[
            int,
            Query(
                description=f"Rows to return, clamped to 1..{LIST_LIMIT_MAX} "
                f"(default {LIST_LIMIT})."
            ),
        ] = LIST_LIMIT,
        offset: Annotated[
            int, Query(description="Rows to skip before the first one returned; clamped to >= 0.")
        ] = 0,
        cursor: Annotated[
            int | None,
            Query(
                description="Id of the last row you already saw; answers the rows after it. "
                "Use instead of ?offset, never alongside it."
            ),
        ] = None,
        **filters: Any,
    ) -> Any:
        # ``?format=csv`` is answered at this one registration point rather than
        # by a second route per entity: every list route is created here, so an
        # entity added later is exportable by construction and nobody has to
        # remember. FastAPI hands a Response straight back, response_model and
        # all, so the json branch below is untouched byte for byte.
        #
        # Every query parameter is checked against the vocabulary the mapper
        # derived above -- a misspelling used to answer 200 with the whole
        # table, silently, because nothing ever looked at the query string at
        # all. Refused BEFORE the read, naming what it did not recognise.
        unknown = set(request.query_params) - accepted
        if unknown:
            raise HTTPException(422, f"unknown query parameter(s): {', '.join(sorted(unknown))}")
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
        # Two different ways to page. Honouring one and ignoring the other would answer
        # 200 with a page the caller reads as the one they asked for -- the same silent
        # wrong answer an unrecognised filter used to give.
        if cursor is not None and start:
            raise HTTPException(422, "send ?cursor or ?offset, not both -- they page differently")
        conditions = _filter_conditions(vocabulary, filters)
        total = db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0
        page = select(model).where(*conditions)
        if cursor is not None:
            page = page.where(key > cursor)
        # One row PAST the window, then trimmed. That extra row is the only honest way to
        # know a next page exists: emitting a cursor whenever the page came back full
        # hands out one that answers empty whenever the total lands on an exact multiple.
        rows = list(
            db.scalars(
                page.order_by(key).offset(0 if cursor is not None else start).limit(window + 1)
            )
        )
        following, rows = len(rows) > window, rows[:window]
        after = getattr(rows[-1], key_attribute) if following and rows else None
        if format == "csv":
            return _windowed(csv_response(out, rows, path.strip("/")), total, window, start, after)
        _windowed(response, total, window, start, after)
        return rows

    # FastAPI reads a route's OWN signature to decide what a request may send, and
    # the derived filters are not literal parameters of ``list_rows`` above (a 30th
    # resource would need one hand-added there) -- so the signature it actually
    # reads is built here instead, in the same "reassign what FastAPI introspects"
    # idiom as ``app.openapi`` below.
    base_params = [*inspect.signature(list_rows).parameters.values()][:-1]  # drop **filters
    list_rows.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        base_params
        + [_query_parameter(name, annotation) for name, _, annotation, _cmp in vocabulary]
    )

    def get_row(row_id: int, db: Db) -> Any:
        return fetch(db, model, row_id)

    app.add_api_route(
        path,
        list_rows,
        methods=["GET"],
        response_model=list[out],
        tags=[tag],
        summary=f"List {model.__name__} rows",
    )
    listing = app.routes[-1]  # the route just registered, before any other touches app.routes
    assert isinstance(listing, APIRoute)  # a registration-time invariant, like schemas.py's
    accepted.update(parameter.name for parameter in listing.dependant.query_params)
    app.add_api_route(
        f"{path}/{{row_id}}",
        get_row,
        methods=["GET"],
        response_model=out,
        tags=[tag],
        summary=f"Get one {model.__name__}",
    )


def writes(
    app: FastAPI,
    path: str,
    model: type[M],
    out: Any,
    patch: type[BaseModel],
    check: Check | None = None,
    delete_check: DeleteCheck | None = None,
    **parents: type[Base],
) -> None:
    """Register the PATCH and DELETE for one entity, both gated by ``If-Match``.

    ``request`` is a plain parameter, not a ``Depends`` -- FastAPI injects the
    live ``Request`` for any handler that names it, which is all
    :func:`_stated_revision` needs to read the header.
    """
    tag = path.strip("/")

    def update_row(row_id: int, payload: BaseModel, db: Db, request: Request) -> Any:
        return _apply(
            db, fetch(db, model, row_id), payload, check, _stated_revision(request), **parents
        )

    def delete_row(row_id: int, db: Db, request: Request) -> None:
        _delete(db, model, row_id, delete_check, _stated_revision(request))

    update_row.__annotations__["payload"] = patch  # a generated twin has no source annotation
    route = f"{path}/{{row_id}}"
    app.add_api_route(
        route,
        update_row,
        methods=["PATCH"],
        response_model=out,
        tags=[tag],
        summary=f"Update a {model.__name__}",
    )
    app.add_api_route(
        route,
        delete_row,
        methods=["DELETE"],
        status_code=204,
        tags=[tag],
        summary=f"Delete a {model.__name__}",
    )


def creates(
    app: FastAPI,
    path: str,
    model: type[M],
    payload_type: type[BaseModel],
    out: Any,
    check: CreateCheck | None = None,
    **parents: type[Base],
) -> None:
    """Register a POST that validates named parents exist, then writes the row.

    The body type is attached at registration exactly as ``writes`` does for
    patches: a create's validation *is* its request schema, so FastAPI needs the
    annotation but there is nothing bespoke to write out per entity.
    """
    tag = path.strip("/")

    def create_row(payload: BaseModel, db: Db) -> Any:
        if check is not None:
            check(db, payload)
        return insert(db, model, payload, **parents)

    create_row.__annotations__["payload"] = payload_type
    app.add_api_route(
        path,
        create_row,
        methods=["POST"],
        response_model=out,
        status_code=201,
        tags=[tag],
        summary=f"Create a {model.__name__}",
    )
