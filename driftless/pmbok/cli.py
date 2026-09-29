"""The ``driftless pmbok`` command: query the ITTO catalog.

``driftless pmbok processes [--area A] [--group G]`` lists the matching processes with
their ITTOs; ``driftless pmbok show ID`` prints one process in full; ``driftless pmbok
support`` prints the store-wide support-coverage summary ``pmbok.support.build_coverage``
computes — how many techniques are explained and how many processes are assessable or
producible, never a count typed here. Read-only over static reference data, so it needs
no database. Registered onto the top-level CLI by ``add_pmbok_subparser``, the same
shape ``report`` uses.

A technique is printed as ``definitions.TECHNIQUES``' ``display_name`` rather than its
catalog key, so this reads the way the web library, ``driftless assess`` and the report
already do — the registry is imported, never a second spelling written here, which is
what keeps the terms of art its overrides fix ("To-Complete Performance Index") right in
the terminal too. Inputs and outputs stay their ``ARTIFACT_KINDS`` keys: nothing owns a
display name for an artifact kind, and the key is the handle a reader carries onward to
``driftless wizard apply --kind``.

A process's ``[group / area]`` header is the same call for the same reason: ``--group``
and ``--area`` accept exactly the enum values, so ``monitoring_controlling`` is a handle
a reader types back rather than an identifier they must decode. Unlike an artifact kind
that reason was never written down, and no guard checked it, which is how the one
multi-word value in either enum sat in reader-facing output unremarked while every other
surface moved to the registry's words. ``tests/test_pmbok_cli.py`` now walks both enums
and runs the CLI with each value, so the justification is rechecked rather than trusted:
if the flag ever stops accepting a value this prints, that is a leak and it fails.

Refusals go to stderr and exit 2, matching every sibling CLI in the package, so a
caller can pipe the catalog on stdout without an error message contaminating it.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from driftless.cli_support import resolve_project
from driftless.db import new_engine, new_session_factory
from driftless.db.config import database_url
from driftless.models import Project
from driftless.pmbok import catalog, proof_checks
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.model import KnowledgeArea, Process, ProcessGroup
from driftless.pmbok.proof import build_proof
from driftless.pmbok.support import build_coverage


def _techniques(keys: tuple[str, ...]) -> str:
    """The techniques a process names, in the registry's words.

    ``TECHNIQUES`` covers ``TT_CATALOG`` exactly and the catalog's referential test
    pins that every ``tools_techniques`` entry is a member, so a missing key here is a
    broken catalog rather than a case to render around.
    """
    return ", ".join(TECHNIQUES[key].display_name for key in keys)


def _format(process: Process) -> str:
    """One process as an indented, human-readable block."""
    lines = [
        f"{process.id}  {process.name}  [{process.group.value} / {process.area.value}]",
        f"    inputs:  {', '.join(process.inputs) or '(none)'}",
        f"    tools:   {_techniques(process.tools_techniques) or '(none)'}",
        f"    outputs: {', '.join(process.outputs) or '(none)'}",
    ]
    return "\n".join(lines)


def _run_processes(args: argparse.Namespace) -> int:
    """List processes, optionally filtered by area and/or group."""
    rows = catalog.PROCESSES
    if args.area is not None:
        rows = tuple(p for p in rows if p.area is KnowledgeArea(args.area))
    if args.group is not None:
        rows = tuple(p for p in rows if p.group is ProcessGroup(args.group))
    for process in rows:
        print(_format(process))
    print(f"\n{len(rows)} process(es).")
    return 0


def _run_show(args: argparse.Namespace) -> int:
    """Print one process by its PMBOK clause id."""
    try:
        process = catalog.get(args.id)
    except KeyError:
        print(f"error: no process with id {args.id!r}", file=sys.stderr)
        return 2
    print(_format(process))
    return 0


def _run_support(_args: argparse.Namespace) -> int:
    """Print the store-wide support-coverage summary: every figure comes straight
    off ``support.build_coverage()`` rather than being typed here, so it moves with
    the catalog and the registry instead of a copy going stale."""
    summary = build_coverage()
    print(f"techniques: {summary.explained_technique_count}/{summary.technique_count} explained")
    print(
        f"processes:  {summary.assessable_process_count}/{summary.process_count} assessable, "
        f"{summary.producible_process_count}/{summary.process_count} producible"
    )
    return 0


def _run_proof(_args: argparse.Namespace) -> int:
    """Print the totality proof: every count from ``proof.build_proof()``, and the
    offending members for any that is not zero. Nothing here computes a count —
    it only prints what the registry walk already found."""
    proof = build_proof()
    if proof.is_total:
        print("Everything is accounted for.")
        print(f"({len(TECHNIQUES)} techniques, {len(catalog.PROCESSES)} processes tracked.)")
        return 0
    print("Not everything is accounted for:")
    for shape, members in proof.gaps():
        if members:
            print(f"  {shape.label.lower()} ({len(members)}): {', '.join(members)}")
    return 1


_DB_URL_HELP = (
    "SQLAlchemy database URL (default: the DRIFTLESS_DATABASE_URL environment "
    "variable, or the legacy PMHUB_DATABASE_URL / PMHUB_DB_URL aliases)"
)


def _add_db_url_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db-url", default=None, metavar="URL", help=_DB_URL_HELP)


def _open_project(args: argparse.Namespace) -> tuple[Session, Project] | None:
    """Open a session on ``args.db_url`` and resolve ``args.project``, or print a
    refusal and return ``None``. The caller owns the session it gets back."""
    db_url = args.db_url or database_url()
    if not db_url:
        print(
            "error: no database URL — pass --db-url or set DRIFTLESS_DATABASE_URL", file=sys.stderr
        )
        return None
    session = new_session_factory(new_engine(db_url))()
    project = resolve_project(session, args.project)
    if project is None:
        print(f"error: no project named or numbered {args.project!r}", file=sys.stderr)
        session.close()
        return None
    return session, project


def _run_no_typed_status(_args: argparse.Namespace) -> int:
    """``driftless pmbok proof no-typed-status`` — no store needed, the claim is
    about the schema: no rollup-level model carries a typed status/percent column."""
    check = proof_checks.check_no_typed_status(proof_checks.rollup_model_columns())
    print(check.report())
    return 0 if check.passed else 1


def _run_baseline_immutable(args: argparse.Namespace) -> int:
    """``driftless pmbok proof baseline-immutable PROJECT`` — attempt a patch on
    the project's newest approved baseline and grade the refusal. Never commits:
    the session is rolled back and closed either way."""
    opened = _open_project(args)
    if opened is None:
        return 2
    session, project = opened
    try:
        approved = [
            b for b in project.baselines if b.status == "approved" or b.approved_at is not None
        ]
        if not approved:
            print(
                f"error: project {args.project!r} has no approved baseline to test",
                file=sys.stderr,
            )
            return 2
        baseline = max(approved, key=lambda b: b.version)
        check = proof_checks.run_baseline_immutable_check(session, baseline)
        session.rollback()
    finally:
        session.close()
    print(check.report())
    return 0 if check.passed else 1


def _run_forecast(args: argparse.Namespace) -> int:
    """``driftless pmbok proof forecast PROJECT [--seed N]`` — run the seeded
    Monte Carlo completion forecast twice and grade the reproducibility."""
    opened = _open_project(args)
    if opened is None:
        return 2
    session, project = opened
    try:
        as_of = args.as_of if args.as_of is not None else date.today()
        check = proof_checks.run_forecast_check(project, as_of, args.seed)
    finally:
        session.close()
    print(check.report())
    return 0 if check.passed else 1


def _run_process_state(args: argparse.Namespace) -> int:
    """``driftless pmbok proof process-state PROJECT`` — print every catalog
    process with the artifacts that satisfy it, then grade the evidence."""
    opened = _open_project(args)
    if opened is None:
        return 2
    session, project = opened
    try:
        as_of = args.as_of if args.as_of is not None else date.today()
        for line in proof_checks.process_state_lines(project, session, as_of):
            print(line)
        check = proof_checks.run_process_state_check(project, session, as_of)
    finally:
        session.close()
    print(check.report())
    return 0 if check.passed else 1


def _run_reproduce(args: argparse.Namespace) -> int:
    """``driftless pmbok proof reproduce PATH`` — read a saved report or web
    page off disk and verify its reproducibility receipt. Format (markdown
    report vs. saved HTML page) is detected from the content, never the file
    extension, by ``proof_checks.check_reproduce``."""
    path = Path(args.path)
    try:
        saved = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read {args.path!r}: {exc}", file=sys.stderr)
        return 2
    check = proof_checks.check_reproduce(saved)
    print(check.report())
    return 0 if check.passed else 1


def add_pmbok_subparser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``pmbok`` command onto a parent's subparsers."""
    pmbok = commands.add_parser("pmbok", help="query the PMBOK ITTO catalog")
    pmbok_commands = pmbok.add_subparsers(dest="pmbok_command", required=True)

    processes = pmbok_commands.add_parser("processes", help="list processes and their ITTOs")
    processes.add_argument(
        "--area",
        choices=[area.value for area in KnowledgeArea],
        default=None,
        help="filter by knowledge area",
    )
    processes.add_argument(
        "--group",
        choices=[group.value for group in ProcessGroup],
        default=None,
        help="filter by process group",
    )
    processes.set_defaults(handler=_run_processes)

    show = pmbok_commands.add_parser("show", help="show one process by id")
    show.add_argument("id", help="the PMBOK clause number, e.g. 11.2")
    show.set_defaults(handler=_run_show)

    support = pmbok_commands.add_parser(
        "support", help="print the store-wide support-coverage summary"
    )
    support.set_defaults(handler=_run_support)

    proof = pmbok_commands.add_parser(
        "proof",
        help=(
            "check the wedge claims from the command line; bare, prints the catalog totality proof"
        ),
    )
    proof.set_defaults(handler=_run_proof)
    proof_commands = proof.add_subparsers(dest="proof_command")

    no_typed_status = proof_commands.add_parser(
        "no-typed-status",
        help="fail if any rollup-level model carries a typed status/percent column",
    )
    no_typed_status.set_defaults(handler=_run_no_typed_status)

    baseline_immutable = proof_commands.add_parser(
        "baseline-immutable",
        help="attempt a write on a project's approved baseline and grade the refusal",
    )
    baseline_immutable.add_argument("project", help="project name or id")
    _add_db_url_argument(baseline_immutable)
    baseline_immutable.set_defaults(handler=_run_baseline_immutable)

    forecast = proof_commands.add_parser(
        "forecast",
        help="run the seeded Monte Carlo completion forecast twice and grade reproducibility",
    )
    forecast.add_argument("project", help="project name or id")
    forecast.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="date the forecast is computed as of (default: today)",
    )
    forecast.add_argument("--seed", type=int, default=7, help="Monte Carlo seed (default: 7)")
    _add_db_url_argument(forecast)
    forecast.set_defaults(handler=_run_forecast)

    process_state = proof_commands.add_parser(
        "process-state",
        help="print every catalog process with its state and satisfying artifacts",
    )
    process_state.add_argument("project", help="project name or id")
    process_state.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="date the process state is computed as of (default: today)",
    )
    _add_db_url_argument(process_state)
    process_state.set_defaults(handler=_run_process_state)

    reproduce = proof_commands.add_parser(
        "reproduce",
        help="verify a saved report's or web page's reproducibility receipt",
    )
    reproduce.add_argument("path", help="path to a saved markdown report or HTML page")
    reproduce.set_defaults(handler=_run_reproduce)
