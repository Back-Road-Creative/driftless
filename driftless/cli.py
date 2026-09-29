"""The top-level ``driftless`` command.

One entry point over several domains — ``report``, ``pmbok``, ``assess``,
``wizard`` and ``demo``. Each domain contributes a registrar that adds its subcommand and
sets a ``handler`` on the namespace, so this module never grows a monolithic
parser or a dispatch ladder. ``main`` parses, then calls whatever handler the
chosen subcommand set.

This is the packaged console script (``[project.scripts] driftless``). The older
``driftless.report.cli:main`` still works for ``driftless report all`` — it shares the
very same registrar — so nothing that called the report CLI directly breaks.

``main`` is also where a store that cannot answer becomes a sentence rather than a
stack trace: one pre-flight (a SQLite file that does not exist, checked *before*
anything connects, because connecting would create an empty one) and one boundary
that turns a database error or an ambiguous project into a single stderr line and
exit 2. Every subcommand inherits both, so no domain CLI repeats them.
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, OperationalError, ProgrammingError

from driftless.assess.cli import add_assess_subparser
from driftless.auth.cli import add_token_subparser, add_user_subparser
from driftless.cli_support import AmbiguousProject
from driftless.db.config import database_url
from driftless.demo.cli import add_demo_subparser
from driftless.interchange.cli import add_import_subparser
from driftless.mcp.cli import add_mcp_subparser
from driftless.notify.cli import add_notify_subparser
from driftless.pmbok.cli import add_pmbok_subparser
from driftless.report.cli import add_report_subparser
from driftless.wizard.cli import add_wizard_subparser

Registrar = Callable[["argparse._SubParsersAction[argparse.ArgumentParser]"], None]

# Each phase appends its registrar here rather than editing a shared parser body.
_REGISTRARS: tuple[Registrar, ...] = (
    add_report_subparser,
    add_pmbok_subparser,
    add_assess_subparser,
    add_wizard_subparser,
    add_demo_subparser,
    add_import_subparser,
    add_user_subparser,
    add_token_subparser,
    add_mcp_subparser,
    add_notify_subparser,
)


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser, letting every registered domain add its command."""
    parser = argparse.ArgumentParser(
        prog="driftless", description="driftless — one store, computed views"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for register in _REGISTRARS:
        register(commands)
    return parser


_MIGRATE = "run `alembic upgrade head`"
# Every dialect's way of saying "that table is not there".
_NO_SCHEMA = ("no such table", "does not exist", "undefined table")


def _missing_store(args: argparse.Namespace) -> str | None:
    """The refusal for a SQLite URL naming a file that is not there, else ``None``.

    Opening one *creates* it, so a typo used to leave a 0-byte database behind on
    the way to a traceback. Only commands that declare ``--db-url`` are checked —
    ``demo seed`` talks to a running API and opens no store at all.
    """
    if not hasattr(args, "db_url"):
        return None
    configured = args.db_url or database_url()
    if configured is None:
        return None  # the handler's own "no database URL" error still applies
    try:
        url = make_url(configured)
    except ArgumentError:
        return None  # not a URL we can read: let the engine say so
    if not url.drivername.startswith("sqlite") or url.database in (None, "", ":memory:"):
        return None
    path = Path(str(url.database))
    return None if path.exists() else f"error: no database at {path} — {_MIGRATE} to create it"


def _unreadable(failure: OperationalError | ProgrammingError) -> str:
    """One line for a database that answered with an error rather than rows."""
    detail = str(failure.orig if failure.orig is not None else failure).strip().splitlines()[0]
    if any(marker in detail.lower() for marker in _NO_SCHEMA):
        return f"error: no driftless tables in the database ({detail}) — {_MIGRATE}"
    return f"error: the database could not be read: {detail}"


def main(argv: list[str] | None = None) -> int:
    """Parse ``argv`` and run the chosen subcommand's handler. Returns an exit code."""
    args = _build_parser().parse_args(argv)
    handler: object = args.handler
    assert callable(handler)  # every leaf subparser sets one via set_defaults
    refusal = _missing_store(args)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2
    try:
        return int(handler(args))
    except AmbiguousProject as ambiguous:
        print(f"error: {ambiguous}", file=sys.stderr)
        return 2
    except (OperationalError, ProgrammingError) as failure:
        print(_unreadable(failure), file=sys.stderr)
        return 2
