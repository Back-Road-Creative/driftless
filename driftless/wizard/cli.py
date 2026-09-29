"""The ``driftless wizard`` command — the agent-drivable onboarding surface.

Three subcommands: ``next`` prints the next process to work (JSON), ``status``
prints the whole process-state map (JSON), and ``apply`` produces one output.
Producing goes through :func:`~driftless.services.wizard_writes.produce`, which
reuses the API's own validated write path — the Pydantic request schemas plus
``driftless.api.records.insert`` — so a wizard write is validated and audited on
the ChangeLog exactly as an HTTP write is, credited to the ``--actor`` this
command requires. That is why this module (an entry point) may import the API
while the wizard engine stays below it.

The producers themselves live in :mod:`driftless.services.wizard_writes` now,
alongside the status-snapshot and sign-off writes web and API already share —
this module re-exports the names its own callers have always imported from
``driftless.wizard.cli``, so none of them needed to change what they import from.

So the loop that drives this — human or agent — can stand a project up end to
end without touching the database directly: ``next`` says what to make, ``apply``
makes it through the boundary, ``status`` confirms it landed.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from datetime import date

from driftless.cli_support import resolve_project
from driftless.db import new_engine, new_session_factory
from driftless.db.changelog import register_changelog, set_via
from driftless.db.config import database_url
from driftless.pmbok import state
from driftless.pmbok.model import ProcessGroup
from driftless.services import wizard_writes
from driftless.services.wizard_writes import (
    AlreadyBaselined,
    Fields,
    MissingBody,
    MissingField,
    body_kinds,
    produce,
    producible_kinds,
    required_fields,
    seed_fields,
)
from driftless.wizard import engine
from sqlalchemy.orm import Session

#: Attribute access, not an ``ImportFrom`` — ``wizard_writes._NARRATIVE`` stays that
#: module's private table; this is the one caller that reads it off the module object
#: it already imports, the same way it always could.
_NARRATIVE = wizard_writes._NARRATIVE

__all__ = [
    "AlreadyBaselined",
    "Fields",
    "MissingBody",
    "MissingField",
    "add_wizard_subparser",
    "body_kinds",
    "produce",
    "producible_kinds",
    "required_fields",
    "resolve_project",
    "seed_fields",
]


def _open(db_url: str | None) -> Session:
    url = db_url or database_url()
    if not url:
        raise SystemExit(
            "error: no database URL — pass --db-url or set DRIFTLESS_DATABASE_URL "
            "(the legacy PMHUB_DATABASE_URL and PMHUB_DB_URL aliases are still honoured)"
        )
    factory = new_session_factory(new_engine(url))
    register_changelog(factory)  # wizard writes are audited, exactly like the API's
    session = factory()
    set_via(session, "cli")
    return session


def _parse_fields(pairs: list[str] | None) -> Fields:
    fields: Fields = {}
    for pair in pairs or []:
        key, _, value = pair.partition("=")
        fields[key] = value
    return fields


def _run_next(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        project = resolve_project(session, args.project)
        if project is None:
            print(f"error: no project {args.project!r}", file=sys.stderr)
            return 2
        as_of = args.as_of or date.today()
        groups = [ProcessGroup(g) for g in args.group] if args.group else None
        # next_step's per-process scan (state.process_state / mapping.resolve)
        # rides the same cache — mirrors the identical wrap on the web wizard
        # page (driftless.web.wizard_pages.wizard_page).
        with state.prefetched(session, [project]):
            step = engine.next_step(session, project, as_of, groups)
        print(json.dumps(dataclasses.asdict(step) if step is not None else None, indent=2))
    return 0


def _run_status(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        project = resolve_project(session, args.project)
        if project is None:
            print(f"error: no project {args.project!r}", file=sys.stderr)
            return 2
        as_of = args.as_of or date.today()
        # status walks every catalog process (project_process_states), the same
        # store-wide shape the process-map document/page bound with this cache.
        with state.prefetched(session, [project]):
            statuses = engine.status(session, project, as_of)
        print(json.dumps(dict(statuses), indent=2))
    return 0


def _run_apply(args: argparse.Namespace) -> int:
    with _open(args.db_url) as session:
        project = resolve_project(session, args.project)
        if project is None:
            print(f"error: no project {args.project!r}", file=sys.stderr)
            return 2
        as_of = args.as_of or date.today()
        fields = _parse_fields(args.field)
        if args.process is not None:
            fields["origin_process_id"] = args.process
        try:
            row_id = produce(session, project, args.kind, fields, as_of, args.actor)
        except (KeyError, ValueError) as error:
            # Same refusal the browser form answers 422 with, in the CLI's currency: a
            # message on stderr and rc 2. One surface inventing a value the other refuses
            # is how the placeholders outlived the form fix. ValueError catches them all,
            # pydantic's ValidationError included — a bad --field is not a traceback.
            print(f"error: {error}", file=sys.stderr)
            return 2
        print(f"produced {args.kind} (row {row_id})")
    return 0


def add_wizard_subparser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``wizard`` command onto a parent's subparsers."""
    wizard = commands.add_parser("wizard", help="drive project onboarding")
    sub = wizard.add_subparsers(dest="wizard_command", required=True)

    def _common(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--project", required=True, help="project name or id")
        parser.add_argument("--as-of", type=date.fromisoformat, default=None, metavar="YYYY-MM-DD")
        parser.add_argument("--db-url", default=None, metavar="URL")

    nxt = sub.add_parser("next", help="the next process to work, as JSON")
    _common(nxt)
    nxt.add_argument(
        "--group",
        action="append",
        choices=[g.value for g in ProcessGroup],
        help="restrict to these process groups (repeatable)",
    )
    nxt.set_defaults(handler=_run_next)

    stat = sub.add_parser("status", help="the whole process-state map, as JSON")
    _common(stat)
    stat.set_defaults(handler=_run_status)

    apply = sub.add_parser("apply", help="produce one output through the API boundary")
    _common(apply)
    apply.add_argument("--kind", required=True, choices=producible_kinds())
    apply.add_argument(
        "--actor",
        default="cli",
        metavar="NAME",
        help="who the ChangeLog credits this write to (default: 'cli')",
    )
    apply.add_argument(
        "--field",
        action="append",
        metavar="KEY=VALUE",
        help="output field, repeatable; each kind requires the fields it is made of and "
        "the wizard refuses rather than inventing one (prose kinds body=…, risk_register "
        "description=… probability=… impact=…) — see the README for the per-kind list",
    )
    apply.add_argument(
        "--process",
        default=None,
        metavar="ID",
        help="PMBOK clause id of the process raising this output (e.g. 5.6); "
        "validated against the live catalog at the schema boundary",
    )
    apply.set_defaults(handler=_run_apply)
