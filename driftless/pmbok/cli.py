"""The ``driftless pmbok`` command: query the ITTO catalog.

``driftless pmbok processes [--area A] [--group G]`` lists the matching processes with
their ITTOs; ``driftless pmbok show ID`` prints one process in full. Read-only over
static reference data, so it needs no database. Registered onto the top-level CLI
by ``add_pmbok_subparser``, the same shape ``report`` uses.

Refusals go to stderr and exit 2, matching every sibling CLI in the package, so a
caller can pipe the catalog on stdout without an error message contaminating it.
"""

from __future__ import annotations

import argparse
import sys

from driftless.pmbok import catalog
from driftless.pmbok.model import KnowledgeArea, Process, ProcessGroup


def _format(process: Process) -> str:
    """One process as an indented, human-readable block."""
    lines = [
        f"{process.id}  {process.name}  [{process.group.value} / {process.area.value}]",
        f"    inputs:  {', '.join(process.inputs) or '(none)'}",
        f"    tools:   {', '.join(process.tools_techniques) or '(none)'}",
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
