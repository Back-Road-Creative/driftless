"""The progress replay reads ``change_log`` through an index, not by scanning it.

``adapters.progress_history`` reconstructs each task's percentage out of the append-only
log, filtering on ``table_name = 'task' AND row_id = <task id as text>``. With no index
behind that pair SQLite has two ways to answer, and it picks one of them by size: on a
small log it builds a throwaway AUTOMATIC index at query time, and on a larger one it
gives up and SCANs the whole table. Both read the entire log to serve one project, so the
cost of every dashboard grows with the audit trail rather than with the project.

The plan is asserted on the SQL the replay ACTUALLY emits — captured off the engine with
``before_cursor_execute`` and handed straight to ``EXPLAIN QUERY PLAN`` — rather than on a
statement rebuilt here, which could drift from the real one and still pass. The plan words
are SQLite's: ``SEARCH … USING INDEX <name>`` when a real index answers, and ``SCAN`` or
``AUTOMATIC`` when none exists. The second test covers the other half — a store that
already exists gains the index by migration, and the downgrade genuinely gives it back.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, event, inspect

from driftless import models as m
from driftless.assess import adapters
from driftless.db import Base, new_engine, new_session_factory
from driftless.db import changelog as audit

INDEX_NAME = "ix_change_log_table_row_changed"
INDEX_COLUMNS = ("table_name", "row_id", "changed_at")
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
SEEDED_AT = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def audited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Engine, Any]]:
    """A logged store with enough task history that the log is worth indexing."""
    monkeypatch.setattr(audit, "_utcnow", lambda: SEEDED_AT)
    engine = new_engine(f"sqlite:///{tmp_path / 'audited.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    audit.register_changelog(factory)
    with factory() as session:
        portfolio = m.Portfolio(name="Brands", business=m.Business(name="BRC"))
        project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
        stream = m.Workstream(name="GMS", project=project)
        baseline = m.Baseline(project=project, version=1, status="approved")
        tasks = [
            m.Task(name=f"T{n}", workstream=stream, estimate_unit="hours", percent_complete=0)
            for n in range(30)
        ]
        for task in tasks:
            line = m.BaselineLine(baseline=baseline, task=task, planned_cost=100.0)
            line.planned_start, line.planned_finish = date(2026, 1, 1), date(2026, 3, 31)
            session.add(line)
        session.commit()
        for percent in (25, 50, 75):
            for task in tasks:
                task.percent_complete = percent
            session.commit()
        yield engine, project
    engine.dispose()


def _replay_plan(engine: Engine, project: Any) -> list[str]:
    """SQLite's plan for the one ``change_log`` read ``progress_history`` really makes."""
    seen: list[tuple[str, Any]] = []

    def capture(conn: Any, cursor: Any, sql: str, params: Any, ctx: Any, many: bool) -> None:
        if "change_log" in sql and sql.lstrip().upper().startswith("SELECT"):
            seen.append((sql, params))

    with new_session_factory(engine)() as session:
        merged = session.merge(project)
        event.listen(engine, "before_cursor_execute", capture)
        try:
            adapters.progress_history(session, merged)
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        assert len(seen) == 1, f"expected one change_log read, got {len(seen)}"
        sql, params = seen[0]
        rows = session.connection().exec_driver_sql(f"EXPLAIN QUERY PLAN {sql}", params).all()
    return [str(row[-1]) for row in rows]


def test_the_replay_searches_the_index_instead_of_reading_the_whole_log(
    audited: tuple[Engine, Any],
) -> None:
    """The unit: the replay's own SQL resolves ``change_log`` through the declared index."""
    engine, project = audited
    plan = _replay_plan(engine, project)
    change_log_steps = [step for step in plan if "change_log" in step]
    assert change_log_steps, f"no change_log step in the plan at all: {plan}"
    assert all(INDEX_NAME in step for step in change_log_steps), plan
    assert not any("SCAN" in step or "AUTOMATIC" in step for step in change_log_steps), plan


def test_an_existing_store_gains_the_index_and_the_downgrade_gives_it_back(
    tmp_path: Path,
) -> None:
    """Stores built before this revision get the index by migration, reversibly."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'existing.db'}")
    command.upgrade(config, "head")
    engine = new_engine(config.get_main_option("sqlalchemy.url", ""))
    try:
        indexed = {ix["name"]: tuple(ix["column_names"]) for ix in _indexes(engine)}
        assert indexed.get(INDEX_NAME) == INDEX_COLUMNS, indexed
        # Below the index revision by id, not "-1" from head: the head moves with every
        # later migration; the property is that THIS revision's downgrade removes it.
        command.downgrade(config, "a3f7c95d21e8")  # pragma: allowlist secret  (revision id)
        assert INDEX_NAME not in {ix["name"] for ix in _indexes(engine)}
    finally:
        engine.dispose()


def _indexes(engine: Engine) -> list[Any]:
    """``change_log``'s indexes, read fresh so a downgrade is not served from cache."""
    return list(inspect(engine).get_indexes("change_log"))
