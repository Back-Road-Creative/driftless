"""Honour ``Idempotency-Key`` on writes, so a retried POST cannot create a second row.

At the chokepoint every write passes -- :class:`driftless.api.secure.TokenGate`'s argument
for auth, that a route added later is covered whether anyone remembers or not.

The ORDER is the design: the key is RESERVED in its own transaction before the request runs
(the UNIQUE constraint on ``key`` is what prevents the duplicate), the response stored after.
So a retry meets one of two states. With a stored response the first attempt finished and the
client never heard -- replay it, touching nothing. With NO stored response it died between
writing and answering, so **the write may have landed**; re-running is the duplicate this
prevents, and ``409`` says exactly that, because an outcome a human resolves beats a silent
second row nobody sees until a report reads wrong. A key replayed on a different method or
path is ``422``: another endpoint's body would hide a client bug.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from driftless.db.session import session_scope
from driftless.models.idempotency import IdempotencyRecord

HEADER = "Idempotency-Key"
#: Outside this set is a write and participates -- an unlisted method fails INTO the
#: mechanism, the same direction ``secure._READ_METHODS`` fails.
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_UNKNOWN_OUTCOME = (
    "a request with this Idempotency-Key did not finish; its outcome is unknown, so it "
    "was not retried -- read the resource to see whether the write landed"
)


def install_idempotency(app: FastAPI) -> None:
    """Wire the gate onto ``app``, in the ``install_request_log`` / ``install_metrics`` idiom."""

    @app.middleware("http")
    async def _idempotent(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        key = request.headers.get(HEADER)
        if not key or request.method in _READ_METHODS:
            return await call_next(request)

        path, method = request.url.path, request.method
        with session_scope() as db:
            seen = db.scalars(select(IdempotencyRecord).where(IdempotencyRecord.key == key)).first()
            if seen is not None:
                if (seen.method, seen.path) != (method, path):
                    return JSONResponse(
                        {"detail": f"{HEADER} already used for {seen.method} {seen.path}"}, 422
                    )
                if seen.response_body is None:
                    return JSONResponse({"detail": _UNKNOWN_OUTCOME}, 409)
                return JSONResponse(
                    json.loads(seen.response_body),
                    seen.status_code or 200,
                    {"Idempotent-Replay": "true"},
                )
            db.add(IdempotencyRecord(key=key, method=method, path=path))

        response = await call_next(request)
        # Drained, not forwarded: a body iterator is consumable once, so storing it means
        # rebuilding what the client gets from the bytes.
        body = b"".join([chunk async for chunk in response.body_iterator])  # type: ignore[attr-defined]
        with session_scope() as db:
            record = db.scalars(
                select(IdempotencyRecord).where(IdempotencyRecord.key == key)
            ).first()
            if record is not None:
                record.status_code = response.status_code
                # Only JSON is stored; anything else (an HTML refusal, a CSV export)
                # leaves the reservation outcome-less, so a retry gets the honest 409.
                json_body = "application/json" in response.headers.get("content-type", "")
                record.response_body = body.decode() if json_body else None
        return Response(
            body,
            response.status_code,
            dict(response.headers),
            response.media_type,
        )
