"""The core revision must apply and reverse cleanly, and keep its constraints.

Scope note, because it is easy to add the wrong assertion here: this revision is
the first of a chain and deliberately does not cover the whole schema. Asserting
that ``alembic check`` is clean, or that the migrated database equals
``Base.metadata``, would be red by construction until the records revision lands.
That parity proof belongs at head, in the revision that closes the chain.

What is worth proving now is that this half stands on its own — it applies, it
reverses, and the named CHECK and UNIQUE constraints survived the trip through
autogenerate rather than being quietly dropped.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, UniqueConstraint, inspect

import driftless.models  # noqa: F401  -- registers the tables this revision creates
from driftless.db import Base, new_engine

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

#: Pinned deliberately rather than using "head". This revision is the first of a
#: chain, so "head" stops meaning "this revision" the moment another one lands,
#: and a test that says "head creates exactly these ten tables" would start
#: failing on the next revision rather than on a real regression.
CORE_REVISION = "8980cbcb2fbb"

CORE_TABLES = {
    "business",
    "portfolio",
    "program",
    "project",
    "workstream",
    "task",
    "baseline",
    "baseline_line",
    "milestone",
    "sprint",
}


def _config(url: str) -> Config:
    """Alembic config for ``url``, injected rather than taken from the environment."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _named_constraints(kind: type) -> set[tuple[str, str]]:
    """``(table, constraint name)`` the models expect on the core tables."""
    return {
        # SQLAlchemy types an unnamed constraint's name as a sentinel rather than
        # None, so the truthiness check above is what makes str() honest here.
        (table, str(constraint.name))
        for table in CORE_TABLES
        for constraint in Base.metadata.tables[table].constraints
        if isinstance(constraint, kind) and constraint.name
    }


@pytest.fixture
def url(tmp_path: Path) -> Iterator[str]:
    """A SQLite database migrated to this revision — not to whatever head becomes."""
    database = f"sqlite:///{tmp_path / 'core.db'}"
    command.upgrade(_config(database), CORE_REVISION)
    yield database


def test_upgrade_creates_exactly_the_core_tables(url: str) -> None:
    """The revision builds its ten tables and nothing it does not own."""
    engine = new_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) == CORE_TABLES | {"alembic_version"}
    finally:
        engine.dispose()


def test_upgrade_keeps_every_named_constraint(url: str) -> None:
    """Autogenerate dropped no named CHECK or UNIQUE on the way into the revision."""
    engine = new_engine(url)
    try:
        inspector = inspect(engine)
        checks = {
            (table, check["name"])
            for table in CORE_TABLES
            for check in inspector.get_check_constraints(table)
            if check["name"]
        }
        uniques = {
            (table, unique["name"])
            for table in CORE_TABLES
            for unique in inspector.get_unique_constraints(table)
            if unique["name"]
        }
    finally:
        engine.dispose()

    assert checks == _named_constraints(CheckConstraint)
    assert uniques == _named_constraints(UniqueConstraint)


def test_downgrade_removes_every_table_it_created(url: str) -> None:
    """``downgrade`` is a real inverse, not a ``pass`` that leaves the schema behind."""
    command.downgrade(_config(url), "base")
    engine = new_engine(url)
    try:
        assert inspect(engine).get_table_names() == ["alembic_version"]
    finally:
        engine.dispose()
