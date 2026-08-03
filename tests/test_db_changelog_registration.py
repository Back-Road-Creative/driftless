"""Regression: importing ``driftless.db`` must register the ChangeLog audit table.

The append-only ChangeLog is the "every write is audited" guarantee. Its table is
created for production by an alembic migration, but a create_all-built store (the seed
script, dev and test DBs) only carries the tables that live on ``Base.metadata`` at the
moment ``create_all`` runs. If ``driftless.db.changelog`` is imported *after* that — the way
the API activates auditing on its first request — the schema is already built without
``change_log`` and the first audited write dies with ``no such table: change_log``.

``Base.metadata`` is process-global, so a sibling test module that imports the changelog
module at collection time would register the table in *this* process and hide the bug. Both
checks therefore run in a fresh interpreter, which also reproduces the real create_all-then-
activate ordering exactly.
"""

import os
import subprocess
import sys
from pathlib import Path

# The service checkout (parent of ``tests/``), pinned onto the child's import path so it
# exercises THIS tree rather than the site-packages install.
_SERVICE_DIR = Path(__file__).resolve().parent.parent

# Importing the package alone must be enough to register the audit table.
_CHECK_REGISTRATION = """
import driftless.db

assert "change_log" in driftless.db.Base.metadata.tables, "change_log missing from Base.metadata"
print("OK")
"""

# The real failure path: build the schema from what metadata knows, then activate auditing
# (as the API does) and write one row. Pre-fix the table is absent from the create_all store
# and the flush listener raises; post-fix the row lands.
_CHECK_CREATE_ALL_STORE = """
import driftless.db
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business  # registers the domain tables on the metadata

engine = new_engine("sqlite://")
Base.metadata.create_all(engine)  # builds only what metadata knows at THIS point

from sqlalchemy import func, select

from driftless.db.changelog import ChangeLog, register_changelog  # activation, as the API does

factory = new_session_factory(engine)
register_changelog(factory)
with factory() as db:
    db.add(Business(name="Back Road Creative"))
    db.commit()
    count = db.scalar(select(func.count()).select_from(ChangeLog))

assert count == 1, f"expected one change_log row, got {count!r}"
print("OK")
"""


def _run(code: str) -> subprocess.CompletedProcess[str]:
    """Run ``code`` in a fresh interpreter pinned to this checkout."""
    env = {**os.environ, "PYTHONPATH": str(_SERVICE_DIR)}
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=_SERVICE_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


def test_importing_driftless_db_registers_the_change_log_table() -> None:
    result = _run(_CHECK_REGISTRATION)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("OK")


def test_a_create_all_store_can_write_the_audit_log() -> None:
    result = _run(_CHECK_CREATE_ALL_STORE)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("OK")
