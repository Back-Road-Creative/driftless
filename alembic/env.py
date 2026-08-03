"""Alembic environment: migrations are compared against the models themselves.

The imports below are what makes this file work. Each one registers its tables
on ``Base.metadata``, and ``target_metadata`` *is* that object — so
``--autogenerate`` and ``alembic check`` measure a candidate schema against the
ORM rather than against a hand-kept second copy of it. Drop an import and the
comparison silently stops seeing those tables and reports that all is well.

``driftless.db.changelog`` needs naming separately: it holds ``change_log``, which
``driftless.models`` does not re-export because activation of its flush listener is
deliberately explicit. The table is still part of the schema — the listener
inserts into it on every write — so a baseline generated from ``driftless.models``
alone omits it, and the first audited write after deploy fails on a missing
table.

The URL is never hardcoded and never read at import time. ``_database_url``
runs only once a migration actually starts, so importing this module — or
running a subcommand that touches no database — does not require the
environment to be configured.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import driftless.db.changelog  # noqa: F401  -- registers change_log; see the docstring
import driftless.models  # noqa: F401  -- registers the other seventeen tables
from alembic import context
from driftless.db import Base
from driftless.db.config import CANONICAL_ENV, database_url

DATABASE_URL_ENV = CANONICAL_ENV

config = context.config

if config.config_file_name is not None:
    # Alembic runs inside pytest as well as standalone; leaving existing loggers
    # alone keeps it from tearing down the test runner's own logging.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    """The database to migrate: an injected config value, else the environment."""
    injected = config.get_main_option("sqlalchemy.url", None)
    if injected:
        return injected
    url = database_url()
    if not url:
        raise RuntimeError(
            f"{DATABASE_URL_ENV} is unset — point it at the database to migrate: "
            "a postgresql+psycopg:// URL for host:5432/driftless (the legacy "
            "PMHUB_DATABASE_URL and PMHUB_DB_URL aliases are still honoured). "
            "Credentials belong in that environment variable, never in this "
            "file — spelling the example out in full made CI's secret scanner "
            "read it as a real basic-auth credential."
        )
    return url


def run_migrations_offline() -> None:
    """Emit the SQL without connecting, for review or a DBA-applied change."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and apply.

    ``render_as_batch`` matters only on SQLite, which cannot ALTER a table and
    needs Alembic's copy-and-swap; Postgres alters in place.
    """
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
