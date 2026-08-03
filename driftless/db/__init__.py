"""Database plumbing: the declarative base, engines and session factories.

Importing this package also registers the ``ChangeLog`` audit table on
``Base.metadata`` (via the ``driftless.db.changelog`` re-export below), so any
``create_all``-built store — the seed script, dev and test DBs — carries
``change_log`` and every audited write has somewhere to go. Importing only runs
the model's class body; it does not activate the flush listener, which stays
explicit through ``register_changelog``.
"""

from driftless.db.base import Base, new_engine, new_session_factory
from driftless.db.changelog import ChangeLog

__all__ = ["Base", "ChangeLog", "new_engine", "new_session_factory"]
