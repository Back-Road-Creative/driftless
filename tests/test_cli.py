"""The top-level ``driftless`` CLI dispatches to the domain handlers.

Five domains register here (``report``, ``pmbok``, ``assess``, ``wizard``,
``demo``); this test only exercises ``report``, pinning that ``driftless report
all`` runs through the new entry point exactly as it did through
``driftless.report.cli``, so repointing the console script broke nothing, and
that an unknown command is a clean argparse error rather than a traceback.
"""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from driftless import cli
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business, CostEntry, Portfolio, Project, Task, Workstream
from driftless.models import Baseline, BaselineLine
from datetime import date

JAN, MAR = date(2026, 1, 31), date(2026, 3, 31)


def _seed_db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        _seed(session)
    return url


def _seed(session: Session) -> None:
    portfolio = Portfolio(name="Content Brands", business=Business(name="BRC"))
    proj = Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    stream = Workstream(name="GMS", project=proj)
    task = Task(name="GMS", workstream=stream, estimate_unit="hours", percent_complete=50)
    baseline = Baseline(project=proj, version=1, status="approved")
    line = BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
    line.planned_start, line.planned_finish = JAN, MAR
    session.add(line)
    session.add(CostEntry(project=proj, category="labour", incurred_on=JAN, amount=400.0))
    session.commit()


def test_driftless_report_all_runs_through_the_top_level_cli(tmp_path: Path) -> None:
    url = _seed_db(tmp_path)
    out = tmp_path / "reports"
    rc = cli.main(["report", "all", "--as-of", "2026-03-31", "--out", str(out), "--db-url", url])
    assert rc == 0
    assert (out / "2026-03-31" / "gms" / "cost-evm.md").exists()


def test_unknown_command_is_an_argparse_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["nonsense"])


def test_no_command_is_an_argparse_error() -> None:
    with pytest.raises(SystemExit):
        cli.main([])


def test_entry_point_resolves_to_the_top_level_main() -> None:
    """The packaged console script points here, not at the report CLI."""
    from importlib.metadata import entry_points

    scripts = entry_points(group="console_scripts")
    driftless = next((e for e in scripts if e.name == "driftless"), None)
    assert driftless is not None and driftless.value == "driftless.cli:main"


def test_wizard_and_assess_clis_share_one_project_resolver() -> None:
    """``assess`` and ``wizard`` both resolve a project by id-or-name the exact same
    way — one shared function, not two byte-identical copies that could drift."""
    from driftless.assess.cli import resolve_project as assess_resolve
    from driftless.wizard.cli import resolve_project as wizard_resolve

    assert assess_resolve is wizard_resolve
