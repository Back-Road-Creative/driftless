"""The ``driftless report all`` command: regenerate every discovered document.

This is the *only* place in driftless that reads the wall clock — ``--as-of``
defaults to ``date.today()`` here so templates and ``gather`` never touch it.
Each document declares its ``SCOPE``: project-scoped documents (the default,
``render(session, project, as_of)``) render once per project; business-scoped
documents (``render(session, as_of)``) render once for the whole store. Output
lands under ``<out>/<as-of>/`` — per project under a slugified subdirectory,
business docs at the as-of root — and, because nothing reads the clock past the
resolved ``as_of``, regenerates byte-identically. Every written document carries
a trailing reproducibility receipt (``driftless.report.receipt``) naming the
as-of, schema revision, build SHA and a sha256 of the document itself.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.assess import engine as assess_engine
from driftless.db import new_engine, new_session_factory
from driftless.db.config import database_url
from driftless.models import Project
from driftless.pmbok import state
from driftless.report import engine
from driftless.report.receipt import attach_markdown_receipt


def _slugify(name: str) -> str:
    """Lowercase and hyphenate a project name into a filesystem-safe directory."""
    return name.strip().lower().replace(" ", "-")


def _write(path: Path, text: str) -> None:
    """Create parent directories and write ``text`` to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _render_all(session: Session, out: Path, as_of: date) -> list[Path]:
    """Render every discovered document, dispatching on its ``SCOPE``, and return
    the paths written. Project-scoped documents render once per project (name
    order); business-scoped documents render once for the whole store.

    The one project query carries ``adapters.eager_project()`` — the same options
    every web route over this walk applies — so the EVM documents never lazy-load
    ``line.task`` per baseline line, and the loop runs inside one set of prefetch
    scopes so per-project evaluator and process-state reads batch across the
    store. ``state.prefetched`` caches PROCESS sign-offs only, so
    ``engine.threat_sign_offs`` joins it for the THREAT ledger the Assessment
    Report's per-threat ``is_suppressed`` calls read — one pass for the run
    instead of a query per threat per project. The scopes change how many
    statements run, never which rows come back, so the bytes are unchanged
    (``tests/test_perf_report_all.py`` and
    ``tests/test_perf_report_signoff_scope.py`` pin both halves)."""
    root = out / as_of.isoformat()
    projects = list(
        session.scalars(
            select(Project).order_by(Project.name, Project.id).options(*adapters.eager_project())
        )
    )
    written: list[Path] = []
    with (
        adapters.prefetched(session, projects),
        state.prefetched(session, projects),
        assess_engine.threat_sign_offs(session),
    ):
        for module in engine.iter_documents():
            slug = module.SLUG
            assert isinstance(slug, str)  # the document contract
            if getattr(module, "SCOPE", "project") == "business":
                text = module.render(session, as_of)
                assert isinstance(text, str)
                path = root / f"{slug}.md"
                _write(path, attach_markdown_receipt(text, as_of))
                written.append(path)
            else:
                for project in projects:
                    text = module.render(session, project, as_of)
                    assert isinstance(text, str)
                    path = root / _slugify(project.name) / f"{slug}.md"
                    _write(path, attach_markdown_receipt(text, as_of))
                    written.append(path)
    return written


def add_report_subparser(commands: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Register the ``report`` command onto a parent's subparsers.

    Shared by the standalone ``driftless.report.cli`` parser and the top-level
    ``driftless`` CLI, so ``driftless report all`` means the same thing whichever entry
    point runs it. The leaf sets ``handler`` on its namespace, so the caller
    dispatches with ``args.handler(args)`` and never re-branches on the command.
    """
    report = commands.add_parser("report", help="generate reports")
    report_commands = report.add_subparsers(dest="report_command", required=True)
    render = report_commands.add_parser("all", help="render every document for every project")
    render.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="date the figures are computed as of (default: today)",
    )
    render.add_argument(
        "--out",
        type=Path,
        default=Path("reports"),
        metavar="DIR",
        help="output directory (default: reports/)",
    )
    render.add_argument(
        "--db-url",
        default=None,
        metavar="URL",
        help=(
            "SQLAlchemy database URL (default: the DRIFTLESS_DATABASE_URL environment "
            "variable, or the legacy PMHUB_DATABASE_URL / PMHUB_DB_URL aliases)"
        ),
    )
    render.set_defaults(handler=_run_report_all)


def _build_parser() -> argparse.ArgumentParser:
    """Build the standalone ``driftless report all`` argument parser (back-compat)."""
    parser = argparse.ArgumentParser(prog="driftless", description="driftless document tools")
    commands = parser.add_subparsers(dest="command", required=True)
    add_report_subparser(commands)
    return parser


def _run_report_all(args: argparse.Namespace) -> int:
    """Render every document for every project. The ``report all`` handler."""
    db_url: str | None = args.db_url or database_url()
    if not db_url:
        print(
            "error: no database URL — pass --db-url or set DRIFTLESS_DATABASE_URL "
            "(the legacy PMHUB_DATABASE_URL and PMHUB_DB_URL aliases are still honoured)",
            file=sys.stderr,
        )
        return 2

    as_of: date = args.as_of if args.as_of is not None else date.today()
    out: Path = args.out

    db_engine = new_engine(db_url)
    with new_session_factory(db_engine)() as session:
        written = _render_all(session, out, as_of)

    print(f"Wrote {len(written)} document(s) under {out / as_of.isoformat()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the standalone ``driftless report`` parser. Returns an exit code."""
    args = _build_parser().parse_args(argv)
    handler: object = args.handler
    assert callable(handler)
    return int(handler(args))
