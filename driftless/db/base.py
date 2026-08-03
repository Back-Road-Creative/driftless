"""Declarative base, engine construction and the SQLite foreign-key pragma.

The whole hierarchy rests on "each child has exactly one parent, enforced by
the database". SQLite defaults ``foreign_keys`` to OFF *per connection*, so
without the listener below every FK would be advisory: orphan rows would insert
happily and the guarantee would be silently void.
"""

import sqlite3
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base shared by every driftless table."""


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
    """Turn FK enforcement on per SQLite connection; other dialects always enforce."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


#: Starlette's default AnyIO worker-thread limiter: this many sync ``def`` handlers can
#: hold a connection at once, so the pool covers exactly that bound. Smaller (the old
#: 5+10) meant the 16th concurrent request waited ``pool_timeout``, then 500ed.
STARLETTE_THREADPOOL_TOKENS = 40


def new_engine(url: str) -> Engine:
    """Build an engine for ``url``. Schema creation is the caller's business.

    ``pool_pre_ping`` replaces a dead connection at checkout, so the first request after
    a database restart reconnects instead of failing; ``pool_recycle`` retires one before
    any idle-timeout between here and the store does it mid-request. SQLite keeps its
    dialect-chosen pool: the sizing kwargs belong to ``QueuePool``, which the in-memory
    pool does not take, and a file store serves one dev process, not a threadpool.
    """
    kwargs: dict[str, Any] = {"pool_pre_ping": True, "pool_recycle": 1800}
    if not url.startswith("sqlite"):
        kwargs["pool_size"] = 10  # kept warm; the rest open on demand and close back down
        kwargs["max_overflow"] = STARLETTE_THREADPOOL_TOKENS - 10
    return create_engine(url, **kwargs)


def new_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a session factory bound to ``engine``."""
    return sessionmaker(bind=engine)
