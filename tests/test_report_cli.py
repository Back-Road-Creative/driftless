"""The ``driftless report all`` CLI: it discovers every document, renders project-scoped
ones once per project and business-scoped ones once, writes them under
``<out>/<as-of>/``, and regenerates byte-identically."""

import types
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.db import Base, new_engine, new_session_factory
from driftless.report import cli
from driftless.report import engine as report_engine

AS_OF = date(2026, 3, 31)  # matches the seeded baseline finish
JAN = date(2026, 1, 31)


def _seed(session: Session) -> None:
    """Two projects under one portfolio, each with the conftest figure set
    (BAC 1000, EV 500, AC 400)."""
    business = m.Business(name="BRC")
    portfolio = m.Portfolio(name="Content Brands", business=business)
    for name in ("BTB", "GMS"):
        proj = m.Project(name=name, portfolio=portfolio, delivery_mode="predictive")
        stream = m.Workstream(name=name, project=proj)
        task = m.Task(name=name, workstream=stream, estimate_unit="hours", percent_complete=50)
        baseline = m.Baseline(project=proj, version=1, status="approved")
        line = m.BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
        line.planned_start, line.planned_finish = JAN, AS_OF
        session.add(line)
        session.add(m.CostEntry(project=proj, category="labour", incurred_on=JAN, amount=400.0))
    session.commit()


def _seed_db(tmp_path: Path) -> str:
    """Build a seeded SQLite database and return its SQLAlchemy URL."""
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        _seed(session)
    return url


def test_report_all_writes_per_project_documents(tmp_path: Path) -> None:
    url = _seed_db(tmp_path)
    out = tmp_path / "reports"
    rc = cli.main(["report", "all", "--as-of", "2026-03-31", "--out", str(out), "--db-url", url])
    assert rc == 0
    cost = out / "2026-03-31" / "gms" / "cost-evm.md"
    assert cost.exists()
    assert "1000.00" in cost.read_text(encoding="utf-8")  # calc's BAC on the leaf
    # every discovered project-scoped document lands once for each project
    assert (out / "2026-03-31" / "btb" / "cost-evm.md").exists()
    assert (out / "2026-03-31" / "gms" / "charter.md").exists()


def test_report_all_is_byte_identical_across_runs(tmp_path: Path) -> None:
    url = _seed_db(tmp_path)
    out = tmp_path / "reports"
    args = ["report", "all", "--as-of", "2026-03-31", "--out", str(out), "--db-url", url]
    assert cli.main(args) == 0
    first = {p.relative_to(out): p.read_bytes() for p in sorted(out.rglob("*.md"))}
    assert cli.main(args) == 0
    second = {p.relative_to(out): p.read_bytes() for p in sorted(out.rglob("*.md"))}
    assert first  # something was written
    assert first == second


def test_report_all_survives_a_legacy_same_day_sprint_row(tmp_path: Path) -> None:
    """A same-day sprint is DB-legal (the CHECK allows ``>=``) but can only reach
    the store as a legacy row predating the API's create/patch refusal; one such
    row must not abort ``report all`` for every project in the store, only skip
    itself out of that project's velocity window."""
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        _seed(session)  # BTB, GMS predictive projects
        portfolio = m.Portfolio(name="Agile", business=m.Business(name="BRC-Agile"))
        agile = m.Project(name="Sprintful", portfolio=portfolio, delivery_mode="agile")
        stream = m.Workstream(name="Epic", project=agile)
        session.add(
            m.Task(name="A", workstream=stream, estimate_unit="points", estimate=5.0, status="todo")
        )
        session.add(
            m.Sprint(
                project=agile, name="Real", start_date=JAN, end_date=AS_OF, completed_points=10
            )
        )
        session.add(
            m.Sprint(
                project=agile,
                name="Legacy",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 1),
                completed_points=999,
            )
        )
        session.commit()

    out = tmp_path / "reports"
    rc = cli.main(["report", "all", "--as-of", "2026-03-31", "--out", str(out), "--db-url", url])
    assert rc == 0
    forecast = out / "2026-03-31" / "sprintful" / "forecast.md"
    assert forecast.exists()
    assert "999.00" not in forecast.read_text(encoding="utf-8")
    # the other two projects in the store rendered too — the legacy row did not abort the batch
    assert (out / "2026-03-31" / "gms" / "forecast.md").exists()
    assert (out / "2026-03-31" / "btb" / "forecast.md").exists()


def test_business_scoped_document_renders_once_not_per_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = _seed_db(tmp_path)  # two projects in the store
    out = tmp_path / "reports"
    calls: list[date] = []

    def fake_render(session: Session, as_of: date) -> str:
        calls.append(as_of)
        return "# Fake Rollup\n"

    fake = types.SimpleNamespace(
        SLUG="fake-rollup", TITLE="Fake Rollup", SCOPE="business", render=fake_render
    )
    monkeypatch.setattr(report_engine, "iter_documents", lambda: iter([fake]))

    rc = cli.main(["report", "all", "--as-of", "2026-03-31", "--out", str(out), "--db-url", url])
    assert rc == 0
    assert calls == [AS_OF]  # once for the whole store, not once per project
    assert list(out.rglob("fake-rollup.md")) == [out / "2026-03-31" / "fake-rollup.md"]
    body = (out / "2026-03-31" / "fake-rollup.md").read_text(encoding="utf-8")
    assert body == "# Fake Rollup\n"


def test_report_all_scans_cost_entries_once(tmp_path: Path) -> None:
    """cost-evm, forecast and weekly-status each render once per project, and
    department once for the store; all four read ``gather.project_costs``,
    which -- unmemoized -- is its own unfiltered ``SELECT ... FROM cost_entry``
    full-table scan every time it is called (3P + 1 = 7 scans on this
    two-project seed). Memoized on the CLI's single read-only session, `report
    all` runs exactly one, no matter how many documents or projects ask.
    Distinguished from the per-project ``adapters.project_costs`` the Cost
    evaluator uses (``WHERE cost_entry.project_id = ...``) by the absence of a
    WHERE clause -- that one is already scoped and out of scope here."""
    url = _seed_db(tmp_path)
    out = tmp_path / "reports"
    scans: list[str] = []

    def _bump(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        text = statement.lower()
        if "from cost_entry" in text and "where" not in text:
            scans.append(statement)

    event.listen(Engine, "before_cursor_execute", _bump)
    try:
        rc = cli.main(
            ["report", "all", "--as-of", "2026-03-31", "--out", str(out), "--db-url", url]
        )
    finally:
        event.remove(Engine, "before_cursor_execute", _bump)

    assert rc == 0
    assert len(scans) == 1, (
        f"report all ran {len(scans)} unfiltered cost_entry scans (expected 1): "
        "gather.project_costs is not memoized per session"
    )


def test_missing_db_url_errors_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PMHUB_DATABASE_URL", raising=False)
    monkeypatch.delenv("PMHUB_DB_URL", raising=False)
    rc = cli.main(["report", "all", "--out", str(tmp_path / "reports")])
    assert rc != 0
    assert "PMHUB_DB_URL" in capsys.readouterr().err
