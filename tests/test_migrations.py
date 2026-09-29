"""At head, the migration chain must build exactly the schema the models describe.

This is the parity proof, and it belongs here rather than in the core revision:
the chain does not cover every table until this revision lands, so asserting
parity any earlier would be red by construction.

Two different questions get asked, because either alone lets real drift through.
``compare_metadata`` is Alembic's own autogenerate diff — the same comparison
``alembic check`` runs — but it ignores CHECK constraints, so a chain that
quietly lost every vocabulary CHECK would still pass it. The second test
therefore reflects both the migrated database and a ``create_all`` database and
compares the DDL directly, CHECKs included.

Both imports below are load-bearing and must match ``alembic/env.py``: they are
what puts tables on ``Base.metadata``. Importing only ``driftless.models`` would
leave this test depending on some other test module having imported the rest,
so it would pass or fail on collection order rather than on the schema.

SQLite alone was never the whole proof: it takes every schema change through
Alembic's copy-and-swap batch mode (``alembic/env.py``), which is the one path
production never runs. So every test below is parametrised over both dialects.
Point ``DRIFTLESS_TEST_DB_URL`` at a Postgres server and the chain is proved
there too — CI's Migrations job does exactly that against a postgres:16 service
container. Unset, the Postgres half skips, so a plain ``pytest`` needs no server.
"""

import os
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, make_url

import driftless.db.changelog  # noqa: F401  -- registers change_log
import driftless.models  # noqa: F401  -- registers the other seventeen tables
from driftless.db import Base, new_engine

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
TEST_DB_URL_ENV = "DRIFTLESS_TEST_DB_URL"

#: Hands back the URL of an empty database of the parametrised dialect, by name.
NewStore = Callable[[str], str]


def _config(url: str) -> Config:
    """Alembic config for ``url``, injected rather than taken from the environment."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _describe(engine: Engine) -> dict[str, object]:
    """Everything about a schema that the models pin down, in comparable form."""
    inspector = inspect(engine)
    described: dict[str, object] = {}
    for table in sorted(inspector.get_table_names()):
        if table == "alembic_version":  # bookkeeping, absent from the models
            continue
        described[table] = {
            "columns": sorted(
                (column["name"], str(column["type"]), column["nullable"])
                for column in inspector.get_columns(table)
            ),
            "primary_key": inspector.get_pk_constraint(table)["constrained_columns"],
            "foreign_keys": sorted(
                (tuple(fk["constrained_columns"]), fk["referred_table"])
                for fk in inspector.get_foreign_keys(table)
            ),
            "unique": sorted(
                (str(uq["name"]), tuple(uq["column_names"]))
                for uq in inspector.get_unique_constraints(table)
            ),
            "checks": sorted(
                (str(check["name"]), " ".join(str(check["sqltext"]).split()))
                for check in inspector.get_check_constraints(table)
            ),
        }
    return described


def _recreated(server: str, name: str) -> str:
    """Drop and recreate ``name`` on the server ``server`` addresses; return its URL.

    Recreated rather than reused: a database left over from a previous run would
    let a chain that no longer builds the schema pass on somebody else's tables.
    """
    admin = create_engine(server, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}"')
            connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    finally:
        admin.dispose()
    return make_url(server).set(database=name).render_as_string(hide_password=False)


@pytest.fixture(params=["sqlite", "postgresql"])
def backend(request: pytest.FixtureRequest) -> str:
    """The dialect this round proves the chain on."""
    return str(request.param)


@pytest.fixture
def new_store(backend: str, tmp_path: Path) -> NewStore:
    """Empty databases of that dialect, made on demand and named by the caller."""
    if backend == "sqlite":
        return lambda name: f"sqlite:///{tmp_path / f'{name}.db'}"
    server = os.environ.get(TEST_DB_URL_ENV, "").strip()
    if not server:
        pytest.skip(f"{TEST_DB_URL_ENV} unset — the Postgres half runs in CI's Migrations job")
    # The worker id keeps two xdist workers off each other's databases; DROP
    # DATABASE on one another's would fail the run rather than skew it, but a
    # suite that cannot run under `-n auto` is a suite CI would have to special-case.
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    return lambda name: _recreated(server, f"driftless_parity_{worker}_{name}")


@pytest.fixture
def migrated(new_store: NewStore) -> Iterator[Engine]:
    """A database built the way production is built: by the whole chain."""
    url = new_store("migrated")
    command.upgrade(_config(url), "head")
    engine = new_engine(url)
    yield engine
    engine.dispose()


def test_the_run_uses_the_backend_it_claims(migrated: Engine, backend: str) -> None:
    """The dialect asked for is the dialect proved — no quiet second SQLite round."""
    assert migrated.dialect.name == backend


def test_head_matches_the_models(migrated: Engine) -> None:
    """Alembic's own diff of the migrated schema against the models is empty."""
    with migrated.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []


def test_head_matches_create_all_including_checks(migrated: Engine, new_store: NewStore) -> None:
    """The migrated DDL equals what ``create_all`` builds — CHECK constraints included."""
    direct = new_engine(new_store("direct"))
    Base.metadata.create_all(direct)
    try:
        assert _describe(migrated) == _describe(direct)
    finally:
        direct.dispose()


def test_the_chain_reverses_completely(migrated: Engine) -> None:
    """``downgrade base`` walks every revision back, leaving no table behind."""
    # `str(URL)` masks the password, so a Postgres round would downgrade a URL
    # whose password is literally `***`; render it out in full instead.
    url = migrated.url.render_as_string(hide_password=False)
    assert len(inspect(migrated).get_table_names()) == 70  # 69 model tables + alembic_version
    command.downgrade(_config(url), "base")
    assert inspect(new_engine(url)).get_table_names() == ["alembic_version"]


def test_the_flow_date_backfill_replays_the_change_log(new_store: NewStore) -> None:
    """Existing rows keep their history: the revision adding ``backlog_item``'s three flow
    dates fills them in from the ``ChangeLog``, and leaves a row it cannot date honestly
    null — what sends that row to the read path's replay instead."""
    config = _config(url := new_store("backfill"))
    command.upgrade(config, "d4f8b3e19a72")  # pragma: allowlist secret  (revision, not a secret)
    engine = new_engine(url)
    moved = '{"changed": {"status": {"new": "%s"}}}'  # one logged status transition; two
    with engine.begin() as connection:  # items follow: one with a whole history, one without
        for statement in (
            "INSERT INTO business (id, name, row_revision) VALUES (1, 'BRC', 1)",
            "INSERT INTO portfolio (id, name, business_id, row_revision) VALUES (1, 'P', 1, 1)",
            "INSERT INTO project (id, name, portfolio_id, delivery_mode, row_revision)"
            " VALUES (1, 'GMS', 1, 'agile', 1)",
            "INSERT INTO backlog_item (id, project_id, title, description, priority, status,"
            " row_revision) VALUES (1, 1, 'Shipped', '', 'should_have', 'done', 1),"
            " (2, 1, 'Untracked', '', 'should_have', 'proposed', 1)",
            "INSERT INTO change_log (table_name, row_id, operation, changed_at, detail) VALUES"
            """ ('backlog_item', '1', 'insert', '2026-06-01 12:00:00',"""
            """ '{"new": {"status": "proposed"}}'),"""
            f" ('backlog_item', '1', 'update', '2026-06-10 12:00:00', '{moved % 'in_progress'}'),"
            f" ('backlog_item', '1', 'update', '2026-06-28 12:00:00', '{moved % 'done'}')",
        ):
            connection.exec_driver_sql(statement)
    command.upgrade(config, "head")

    # Typed columns, not ``exec_driver_sql``: SQLite hands a Date back as a string.
    read = sa.text("SELECT id, created_on, started_on, done_on FROM backlog_item ORDER BY id")
    with engine.connect() as connection:
        dated = connection.execute(
            read.columns(created_on=sa.Date, started_on=sa.Date, done_on=sa.Date)
        ).all()
    engine.dispose()
    assert [tuple(row) for row in dated] == [
        (1, date(2026, 6, 1), date(2026, 6, 10), date(2026, 6, 28)),
        (2, None, None, None),  # no logged history — left for the read path's fallback
    ]
