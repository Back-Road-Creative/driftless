"""Operational hardening of the store: pool sizing, FK indexes, default parity, rollback.

One property per test group: the real engine's pool covers Starlette's 40-token sync
threadpool and pre-pings, so the first request after a database restart reconnects; every
foreign-key column reads through an index or the unique constraint it leads (SQLite
otherwise SCANs the whole child table to answer "the rows of THIS project");
``app_user.session_epoch`` defaults to ``0`` on the migrated and the ``create_all``
topology alike, so one omitted-column insert cannot pass on one store and raise NOT NULL
on the other; and *Rolling back in place* dumps before ``pg_restore --clean`` destroys it.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, UniqueConstraint, inspect, text
from sqlalchemy.pool import QueuePool

import driftless.db.changelog  # noqa: F401  -- registers change_log on Base.metadata
import driftless.models  # noqa: F401  -- registers the other tables
from driftless.db import Base, new_engine

ROOT = Path(__file__).resolve().parents[1]

#: Starlette's default AnyIO worker-thread limiter. Every sync route runs on one of
#: these tokens, so this many handlers can want a connection at the same time.
STARLETTE_THREADPOOL_TOKENS = 40


def test_a_real_engine_pool_covers_the_starlette_threadpool() -> None:
    """Capacity >= the thread limiter, pre-ping on, recycle finite. No connection made."""
    engine = new_engine("postgresql+psycopg://localhost/driftless")
    try:
        pool = engine.pool
        assert isinstance(pool, QueuePool)
        capacity = pool.size() + pool._max_overflow
        assert capacity >= STARLETTE_THREADPOOL_TOKENS, (
            f"pool capacity {capacity} < the {STARLETTE_THREADPOOL_TOKENS} sync handlers "
            "Starlette will run at once — the overflow request waits pool_timeout, then 500s"
        )
        assert pool._pre_ping, "no pre-ping: the first request after a Postgres restart fails"
        assert 0 < pool._recycle, "recycle -1: connections outlive every idle-timeout between here"
    finally:
        engine.dispose()


def test_sqlite_engines_still_construct_and_answer(tmp_path: Path) -> None:
    """The sizing must not break dev and the suite: both SQLite forms still connect."""
    for url in ("sqlite://", f"sqlite:///{tmp_path / 'file.db'}"):
        engine = new_engine(url)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
        engine.dispose()


def _covered(table_name: str, column_name: str) -> bool:
    """Whether the column is indexed, or leads a unique constraint (already a search key)."""
    table = Base.metadata.tables[table_name]
    column = table.columns[column_name]
    if any(list(index.columns)[0] is column for index in table.indexes):
        return True
    return any(
        isinstance(constraint, UniqueConstraint) and list(constraint.columns)[0] is column
        for constraint in table.constraints
    )


def test_every_foreign_key_column_is_indexed_or_leads_a_unique_constraint() -> None:
    unindexed = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.foreign_keys and not _covered(table.name, column.name)
    ]
    assert not unindexed, (
        f"foreign keys with no index behind them: {sorted(unindexed)} — every per-parent "
        "read of these SCANs the whole child table"
    )


#: One probe per shape the dashboards actually filter by: project children, task leaves.
FK_PROBES = (("cost_entry", "project_id"), ("risk", "project_id"), ("task", "workstream_id"))


def _plan(engine: Engine, table: str, column: str) -> str:
    with engine.connect() as connection:
        sql = text(f"EXPLAIN QUERY PLAN SELECT * FROM {table} WHERE {column} = 1")
        return " ".join(str(row[3]) for row in connection.execute(sql))


def test_fk_filters_search_an_index_rather_than_scanning(tmp_path: Path) -> None:
    engine = new_engine(f"sqlite:///{tmp_path / 'built.db'}")
    Base.metadata.create_all(engine)
    try:
        for table, column in FK_PROBES:
            plan = _plan(engine, table, column)
            assert f"USING INDEX ix_{table}_{column}" in plan, f"{table}.{column}: {plan}"
    finally:
        engine.dispose()


def test_session_epoch_default_matches_on_both_topologies(tmp_path: Path) -> None:
    """The migrated store and the ``create_all`` store accept the same omitted-column insert."""
    built = new_engine(f"sqlite:///{tmp_path / 'direct.db'}")
    Base.metadata.create_all(built)
    migrated_url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", migrated_url)
    command.upgrade(config, "head")
    for name, engine in (("create_all", built), ("migrated", new_engine(migrated_url))):
        column = {c["name"]: c for c in inspect(engine).get_columns("app_user")}["session_epoch"]
        assert column["default"] == "'0'", f"{name}: session_epoch default is {column['default']!r}"
        with engine.begin() as connection:  # schema probe: the default must answer for the column
            connection.execute(
                text(
                    "INSERT INTO app_user (username, password_hash, role, is_active, created_at)"
                    " VALUES ('drill', 'x', 'viewer', 1, '2026-01-01 00:00:00')"
                )
            )
            epoch = connection.execute(
                text("SELECT session_epoch FROM app_user WHERE username = 'drill'")
            ).scalar_one()
        assert epoch == 0, f"{name}: an insert omitting session_epoch stored {epoch!r}"
        engine.dispose()


def test_rolling_back_in_place_dumps_the_current_state_first() -> None:
    """``pg_restore --clean`` destroys the live store; the section must bank it first."""
    operations = (ROOT / "OPERATIONS.md").read_text(encoding="utf-8")
    _, heading, tail = operations.partition("### Rolling back in place")
    assert heading, "OPERATIONS.md lost its 'Rolling back in place' section"
    section = tail.partition("\n## ")[0]
    assert "driftless-backup.sh" in section, (
        "Rolling back in place runs pg_restore --clean over the live database with no dump "
        "of what it is about to destroy — bin/driftless-backup.sh must run first"
    )
    assert section.index("driftless-backup.sh") < section.index("pg_restore"), (
        "the pre-dump must come before pg_restore, not after the data is gone"
    )
