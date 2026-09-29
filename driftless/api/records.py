"""Load-or-404 and validated-insert -- the two primitives every route builds writes on.

Both raise :class:`~fastapi.HTTPException` directly rather than returning a
sentinel, which is why they live in the **api** layer and not ``driftless.db``:
that package deliberately imports zero fastapi/starlette (see its module
docstring), so an HTTP-shaped failure cannot be raised from inside it. Pulled
out of ``driftless.api.app`` on its own -- ``fetch`` still has roughly two
dozen call sites there, so this move barely shrinks that module. Its value is
what it unblocks: the domain-rules block still living in ``app.py`` calls
``fetch`` at every rule, and could not move to its own module while ``fetch``
stayed in ``app.py`` without app.py and the rules module importing each other.
This module imports nothing from ``driftless.api.app``, so nothing built on it
can close that cycle from this side.
"""

from typing import TypeVar

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from driftless.db import Base

M = TypeVar("M", bound=Base)


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
