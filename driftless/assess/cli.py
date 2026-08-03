"""The ``driftless assess`` command: print a project's ranked threats and actions.

``driftless assess <project> --as-of D`` runs every knowledge-area evaluator for one
project (by name or id) and prints each assessment with its threats and
recommended actions, in ranked order. Reads a database (``--db-url`` or the
``DRIFTLESS_DATABASE_URL`` environment variable — with the legacy
``PMHUB_DATABASE_URL`` and ``PMHUB_DB_URL`` aliases still honoured — matching
``driftless report``); the as-of date defaults to today at this boundary only,
never inside the pure evaluators.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from driftless.assess import engine
from driftless.assess.model import Assessment
from driftless.cli_support import resolve_project
from driftless.db import new_engine, new_session_factory
from driftless.db.config import database_url


def _format(assessment: Assessment) -> str:
    lines = [f"[{assessment.status.upper():5}] {assessment.kind}  (risk {assessment.risk_score})"]
    for threat in assessment.threats:
        lines.append(f"    ! {threat.description}")
        lines.append(f"      score {threat.score}  ref {threat.source_ref}")
    for action in assessment.actions:
        lines.append(f"    -> {action.label}  [{action.pmbok_tt}]")
    return "\n".join(lines)


def _run_assess(args: argparse.Namespace) -> int:
    """Assess one project and print every knowledge area's reading."""
    db_url: str | None = args.db_url or database_url()
    if not db_url:
        print(
            "error: no database URL — pass --db-url or set DRIFTLESS_DATABASE_URL "
            "(the legacy PMHUB_DATABASE_URL and PMHUB_DB_URL aliases are still honoured)",
            file=sys.stderr,
        )
        return 2
    as_of: date = args.as_of if args.as_of is not None else date.today()

    with new_session_factory(new_engine(db_url))() as session:
        project = resolve_project(session, args.project)
        if project is None:
            print(f"error: no project named or numbered {args.project!r}", file=sys.stderr)
            return 2
        assessments = engine.assess_project(session, project, as_of)
        threats = engine.live_threats(session, project, as_of)
        print(f"Assessment of {project.name} as of {as_of.isoformat()}")
        for assessment in assessments:
            print(_format(assessment))
        print(f"\n{len(threats)} live threat(s) after sign-offs.")
    return 0


def add_assess_subparser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``assess`` command onto a parent's subparsers."""
    assess = commands.add_parser("assess", help="assess a project across all knowledge areas")
    assess.add_argument("project", help="project name or id")
    assess.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="date the assessment is computed as of (default: today)",
    )
    assess.add_argument(
        "--db-url",
        default=None,
        metavar="URL",
        help=(
            "SQLAlchemy database URL (default: the DRIFTLESS_DATABASE_URL environment "
            "variable, or the legacy PMHUB_DATABASE_URL / PMHUB_DB_URL aliases)"
        ),
    )
    assess.set_defaults(handler=_run_assess)
