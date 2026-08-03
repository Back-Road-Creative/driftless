"""The ``driftless assess`` command, end to end over a seeded database.

Doubles as the phase's run-the-surface probe: it drives the real console entry
(`driftless.cli.main(["assess", ...])`) against a project seeded to overspend, and
checks it prints the ranked threats and resolves the project by name and by id.
"""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from driftless import cli
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import (
    Baseline,
    BaselineLine,
    Business,
    CostEntry,
    Portfolio,
    Project,
    Task,
    Workstream,
)

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)


def _seed_db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        _seed(session)
    return url


def _seed(session: Session) -> None:
    """A project overspending: BAC 1000, 20% done, AC 800 -> red cost (CPI 0.25)."""
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = Baseline(project=project, version=1, status="approved")
    line = BaselineLine(
        baseline=baseline, task=task, planned_cost=1000.0, planned_start=JAN, planned_finish=AS_OF
    )
    session.add(line)
    session.add(CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    session.commit()


def test_assess_prints_ranked_threats(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    url = _seed_db(tmp_path)
    rc = cli.main(["assess", "GMS", "--as-of", "2026-03-31", "--db-url", url])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Assessment of GMS" in out
    assert "[RED  ] cost" in out  # the overspend
    assert "live threat(s)" in out


def test_assess_resolves_a_project_by_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url = _seed_db(tmp_path)
    assert cli.main(["assess", "1", "--as-of", "2026-03-31", "--db-url", url]) == 0
    assert "Assessment of GMS" in capsys.readouterr().out


def test_assess_unknown_project_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    url = _seed_db(tmp_path)
    rc = cli.main(["assess", "Nonesuch", "--as-of", "2026-03-31", "--db-url", url])
    assert rc == 2
    assert "no project" in capsys.readouterr().err


def test_assess_requires_a_database_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PMHUB_DATABASE_URL", raising=False)
    monkeypatch.delenv("PMHUB_DB_URL", raising=False)
    rc = cli.main(["assess", "GMS", "--as-of", "2026-03-31"])
    assert rc == 2
    assert "PMHUB_DB_URL" in capsys.readouterr().err
