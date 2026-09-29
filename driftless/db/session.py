"""The database-session lifecycle: one lazily-built factory, borrowed by every caller.

Nothing binds a socket or opens an engine at import time — the factory is built on
first use, so a test can swap it out first (:func:`temporary_factory`) and no import
ever pays for a connection it does not need.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session, sessionmaker

from driftless.db.base import new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.db.config import database_url

_factory: sessionmaker[Session] | None = None


@contextmanager
def temporary_factory(factory: sessionmaker[Session]) -> Iterator[None]:
    """Route app-lifecycle checks to a throwaway factory for one test-client run."""
    global _factory
    previous = _factory
    _factory = factory
    try:
        yield
    finally:
        _factory = previous


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
