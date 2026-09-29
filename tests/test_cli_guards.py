"""What the CLI says when the store cannot answer, instead of a traceback.

Two day-one failures that used to end in a SQLAlchemy stack trace or — worse — a
silent wrong answer: a URL naming no driftless schema (one line naming the fix,
exit 2, and no 0-byte database left behind by the attempt), and two projects
sharing a name, which ``Project.name`` allows and which the CLI must refuse
rather than resolve to the lower id. Both guards live at the top-level entry
point, so every subcommand inherits them — the parametrised case pins that.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from driftless import cli
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business, Portfolio, Project

SCHEMA_LESS_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("assess", "Nope"),
    ("report", "all"),
    ("user", "list"),
    ("wizard", "next", "--project", "Nope"),
)


@pytest.fixture(autouse=True)
def _no_ambient_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every case passes ``--db-url``; an exported one would mask a regression."""
    for name in ("DRIFTLESS_DATABASE_URL", "PMHUB_DATABASE_URL", "PMHUB_DB_URL"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("command", SCHEMA_LESS_COMMANDS, ids=lambda c: c[0])
def test_a_store_without_the_schema_is_answered_not_traced(
    command: tuple[str, ...], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A real file with no driftless tables: one line, exit 2, no stack trace."""
    store = tmp_path / "empty.db"
    sqlite3.connect(store).close()  # a database, just not a driftless one
    argv = [*command, "--db-url", f"sqlite:///{store}"]
    if command[0] == "report":
        argv += ["--out", str(tmp_path / "reports")]

    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert "alembic upgrade head" in err
    assert "Traceback" not in err and err.strip().count("\n") == 0, err


def test_a_missing_sqlite_file_is_refused_before_it_is_created(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Connecting creates the file, so the check happens before anything connects."""
    missing = tmp_path / "missing.db"

    assert cli.main(["assess", "Nope", "--db-url", f"sqlite:///{missing}"]) == 2
    assert not missing.exists(), "failing left an empty database file behind"
    assert "alembic upgrade head" in capsys.readouterr().err


def _two_projects_of_one_name(tmp_path: Path) -> tuple[str, list[int]]:
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        portfolio = Portfolio(name="Content Brands", business=Business(name="BRC"))
        twins = [Project(name="Website Rebuild", portfolio=portfolio) for _ in range(2)]
        session.add_all(twins)
        session.commit()
        return url, sorted(project.id for project in twins)


def test_missing_store_lets_the_engine_say_so_when_the_url_cannot_even_parse() -> None:
    """A ``--db-url`` that is not a URL at all: the pre-flight steps aside rather
    than shadowing whatever error the engine itself would raise."""
    args = argparse.Namespace(db_url="not a url at all")
    assert cli._missing_store(args) is None


def test_missing_store_skips_an_in_memory_sqlite_url() -> None:
    """``sqlite://`` names no file on disk to check for -- the pre-flight has
    nothing to say about it."""
    args = argparse.Namespace(db_url="sqlite://")
    assert cli._missing_store(args) is None


def test_unreadable_falls_back_to_a_generic_line_for_a_non_schema_error() -> None:
    """An operational failure unrelated to a missing table still reads as one
    line, just not the ``alembic upgrade head`` one."""
    failure = OperationalError("SELECT 1", {}, Exception("database is locked"))
    message = cli._unreadable(failure)
    assert message == "error: the database could not be read: database is locked"
    assert "alembic" not in message


def test_two_projects_of_one_name_are_refused_rather_than_guessed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url, ids = _two_projects_of_one_name(tmp_path)

    assert cli.main(["assess", "Website Rebuild", "--db-url", url]) == 2
    err = capsys.readouterr().err
    assert all(str(project_id) in err for project_id in ids), err
    assert "Traceback" not in err


def test_the_id_still_resolves_when_the_name_is_ambiguous(tmp_path: Path) -> None:
    """The escape hatch the refusal points at has to work."""
    url, ids = _two_projects_of_one_name(tmp_path)

    assert cli.main(["assess", str(ids[0]), "--db-url", url]) == 0


def test_a_user_command_with_no_database_url_at_all_refuses_before_opening_anything() -> None:
    """``auth.cli._open``'s own guard: no ``--db-url`` and no env var, so there
    is no URL yet for ``driftless.cli``'s own ``_missing_store`` to inspect —
    ``_missing_store`` explicitly defers ("the handler's own... error still
    applies") to this one instead."""
    with pytest.raises(SystemExit, match="no database URL"):
        cli.main(["user", "list"])


def test_missing_store_lets_an_unparseable_db_url_reach_the_engine() -> None:
    """A ``--db-url`` SQLAlchemy cannot even parse: ``_missing_store`` is a
    SQLite-file existence check, and a URL it cannot read as a URL at all is
    not its guard to refuse — the engine gets to say so instead."""
    args = argparse.Namespace(db_url="not a url at all::::")
    assert cli._missing_store(args) is None


def test_missing_store_ignores_a_non_sqlite_or_in_memory_url() -> None:
    """The file-existence guard only means anything for an ON-DISK SQLite
    file: a server URL (nothing here to check for on THIS machine) and
    ``sqlite://`` (in-memory, no file at all) both fall through unrefused."""
    assert cli._missing_store(argparse.Namespace(db_url="postgresql://user@host/db")) is None
    assert cli._missing_store(argparse.Namespace(db_url="sqlite://")) is None


def test_unreadable_names_a_generic_database_error_outside_the_schema_markers() -> None:
    """``_unreadable``'s fallback line: an ``OperationalError`` whose detail
    matches none of ``_NO_SCHEMA``'s markers (missing table, wrong dialect
    wording) — a locked file, a permissions error, disk corruption — gets
    named for what it is rather than misread as a missing schema."""
    failure = OperationalError("SELECT 1", {}, Exception("disk I/O error"))
    assert cli._unreadable(failure) == "error: the database could not be read: disk I/O error"
