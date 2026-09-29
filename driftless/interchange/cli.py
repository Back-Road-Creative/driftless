"""The ``driftless import`` and ``driftless export`` commands.

``import`` reads ``msproject`` and ``xer`` schedule files, both landing through
:func:`~driftless.interchange.common.write_imported_schedule` — the same
validated write path (schemas + ``api.records.insert``) the API and the
wizard CLI already write through, so an import is audited on the ChangeLog
exactly like any other write. ``import viva-goals`` reads a Viva Goals OKR
CSV export the same way, through
:func:`~driftless.interchange.viva_goals.import_viva_goals`, onto the
existing balanced scorecard instead of a schedule.

``export`` is the inverse, read-only direction: ``driftless export msproject``
writes the approved baseline (``pmbok.schedule_facts``, the same as-of gate
``web.gantt`` reads) back out as MSPDI XML, to standard out.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from sqlalchemy.orm import Session

from driftless.cli_support import resolve_project
from driftless.db import new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.db.config import database_url
from driftless.interchange.common import ImportedSchedule, write_imported_schedule
from driftless.interchange.msproject import export_msproject_xml, parse_msproject_xml
from driftless.interchange.viva_goals import import_viva_goals, parse_viva_goals_csv
from driftless.interchange.xer import parse_xer
from driftless.pmbok.schedule_facts import schedule_facts


def _open(db_url: str | None) -> Session:
    url = db_url or database_url()
    if not url:
        raise SystemExit("error: no database URL — pass --db-url or set DRIFTLESS_DATABASE_URL")
    factory = new_session_factory(new_engine(url))
    register_changelog(factory)  # import writes are audited, exactly like the API's
    return factory()


def _run_import(args: argparse.Namespace, parse: object) -> int:
    assert callable(parse)
    with _open(args.db_url) as session:
        project = resolve_project(session, args.project)
        if project is None:
            print(f"error: no project {args.project!r}", file=sys.stderr)
            return 2
        schedule: ImportedSchedule = parse(args.file)
        tasks = write_imported_schedule(session, project, schedule, workstream_name=args.workstream)
        session.commit()
        print(f"imported {len(tasks)} tasks, {len(schedule.dependencies)} dependencies")
    return 0


def _run_msproject(args: argparse.Namespace) -> int:
    return _run_import(args, parse_msproject_xml)


def _run_xer(args: argparse.Namespace) -> int:
    return _run_import(args, parse_xer)


def _run_viva_goals(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        project = resolve_project(session, args.project)
        if project is None:
            print(f"error: no project {args.project!r}", file=sys.stderr)
            return 2
        scorecard = parse_viva_goals_csv(args.file)
        result = import_viva_goals(session, project, scorecard, dry_run=args.dry_run)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
        print(
            f"{'would import' if args.dry_run else 'imported'} "
            f"{result.objectives_created} objectives, {result.metrics_created} metric "
            f"definitions, {result.observations_created} observations"
        )
    return 0


def _run_export_msproject(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        project = resolve_project(session, args.project)
        if project is None:
            print(f"error: no project {args.project!r}", file=sys.stderr)
            return 2
        as_of: date = args.as_of if args.as_of is not None else date.today()
        facts = schedule_facts(session, project, as_of)
        if facts is None:
            print(
                f"error: no approved baseline for {args.project!r} as of {as_of.isoformat()}",
                file=sys.stderr,
            )
            return 2
        sys.stdout.buffer.write(export_msproject_xml(facts))
    return 0


def add_import_subparser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``import`` command onto a parent's subparsers."""
    imp = commands.add_parser("import", help="import a schedule from another tool")
    sub = imp.add_subparsers(dest="import_command", required=True)

    def _common(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", help="the schedule file to import")
        parser.add_argument("--project", required=True, help="project name or id")
        parser.add_argument(
            "--workstream",
            default="Imported",
            metavar="NAME",
            help="name of the new workstream the imported tasks land under (default: 'Imported')",
        )
        parser.add_argument("--db-url", default=None, metavar="URL")

    msproject = sub.add_parser("msproject", help="import a Microsoft Project XML (MSPDI) file")
    _common(msproject)
    msproject.set_defaults(handler=_run_msproject)

    xer = sub.add_parser("xer", help="import a Primavera P6 XER file")
    _common(xer)
    xer.set_defaults(handler=_run_xer)

    viva_goals = sub.add_parser(
        "viva-goals", help="import a Viva Goals (retired 2025-12-31) OKR CSV export"
    )
    viva_goals.add_argument("file", help="the Viva Goals OKR CSV export to import")
    viva_goals.add_argument("--project", required=True, help="project name or id")
    viva_goals.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be imported without writing anything",
    )
    viva_goals.add_argument("--db-url", default=None, metavar="URL")
    viva_goals.set_defaults(handler=_run_viva_goals)

    # ``driftless.cli`` registers only one interchange entry point; ``export``
    # rides along with it rather than needing a second registrar wired in there.
    add_export_subparser(commands)


def add_export_subparser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``export`` command onto a parent's subparsers."""
    exp = commands.add_parser("export", help="export a baseline schedule to another tool's format")
    sub = exp.add_subparsers(dest="export_command", required=True)

    msproject = sub.add_parser(
        "msproject", help="export the approved baseline as Microsoft Project XML (MSPDI)"
    )
    msproject.add_argument("--project", required=True, help="project name or id")
    msproject.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="date the approved baseline is read as of (default: today)",
    )
    msproject.add_argument("--db-url", default=None, metavar="URL")
    msproject.set_defaults(handler=_run_export_msproject)
