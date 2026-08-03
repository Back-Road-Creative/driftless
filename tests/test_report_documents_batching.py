"""The per-project document bodies stop re-reading the store: the Assessment
Report derives both surfaces from one ``assess_project`` run; Charter, Schedule
and Forecast batch milestones through ``adapters.project_rows``, bytes pinned;
the Department Report's blended rate is capacity-weighted, not a head-average."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from driftless import models as m
from driftless.assess import adapters
from driftless.assess import engine as assess
from driftless.assess.model import Assessment
from driftless.db import Base, new_engine, new_session_factory
from driftless.report.documents import assessment, charter, department, forecast, schedule

AS_OF = date(2026, 3, 31)  # the conftest figure set's window
JAN = date(2026, 1, 31)
N_PROJ = 3
_MILESTONE_DOCS = (charter, schedule, forecast)
# Lowercase-only groups skip the "| Severity | Area | Threat |" header row:
# severities (red/amber) and kinds (cost/integration/...) are vocabulary words.
_THREAT_ROW = re.compile(r"^\| ([a-z]+) \| ([a-z]+) \| ([^|]+) \|$", re.M)


def _overspend(db: Session, project: m.Project) -> None:
    """Push the conftest project's CPI down to 0.42 so cost raises a red threat."""
    db.add(m.CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    db.commit()


def test_assessment_report_runs_the_evaluators_once(
    db: Session, project: m.Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rows and the threat feed each ran the nine evaluators. Once, now."""
    _overspend(db, project)
    calls = {"n": 0}
    real = assess.assess_project

    def spy(session: Session, proj: m.Project, as_of: date) -> tuple[Assessment, ...]:
        calls["n"] += 1
        return real(session, proj, as_of)

    monkeypatch.setattr(assess, "assess_project", spy)
    text = assessment.render(db, project, AS_OF)
    assert "Assessment Report" in text
    assert calls["n"] == 1, (
        f"assess_project ran {calls['n']} times for one Assessment Report render "
        "(expected 1): the rows and the threat feed are computing independently again"
    )


def test_assessment_top_threats_still_equal_the_engines_ranking_and_filter(
    db: Session, project: m.Project
) -> None:
    """The Top threats table must list exactly ``assess.live_threats``'s answer,
    ranked, a suppressed threat filtered out — its knowledge-area row staying."""
    _overspend(db, project)
    cost = {a.kind: a for a in assess.assess_project(db, project, AS_OF)}["cost"].threats[0]
    db.add(
        m.SignOff(
            project=project,
            subject_kind="threat",
            subject_ref=cost.id,
            decision="accepted",
            signal=cost.score,
        )
    )
    db.commit()

    expected = [
        (t.severity, t.kind, t.description) for t in assess.live_threats(db, project, AS_OF)
    ]
    assert expected, "the fixture must leave live threats — an empty feed proves nothing"
    text = assessment.render(db, project, AS_OF)
    top = text.split("## Top threats")[1].split("## Knowledge areas")[0]
    assert [(s, k, d.strip()) for s, k, d in _THREAT_ROW.findall(top)] == expected
    assert cost.description not in top  # signed off: out of the feed
    assert cost.description in text  # but still on the cost area's own row


def _milestone_store() -> tuple[Engine, sessionmaker[Session]]:
    """``N_PROJ`` predictive projects, two milestones each, id order deliberately
    disagreeing with target order so a relapse to id order cannot render the same
    bytes."""
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as db:
        business = m.Business(name="BRC")
        portfolio = m.Portfolio(name="Content Brands", business=business)
        for j in range(N_PROJ):
            proj = m.Project(name=f"Project {j}", portfolio=portfolio, delivery_mode="predictive")
            stream = m.Workstream(name=f"WS{j}", project=proj)
            task = m.Task(
                name=f"T{j}", workstream=stream, estimate_unit="hours", percent_complete=50
            )
            baseline = m.Baseline(project=proj, version=1, status="approved")
            db.add(
                m.BaselineLine(
                    baseline=baseline,
                    task=task,
                    planned_start=JAN,
                    planned_finish=AS_OF,
                    planned_cost=1000.0,
                )
            )
            db.add(m.CostEntry(project=proj, category="labour", incurred_on=JAN, amount=400.0))
            db.add(
                m.Milestone(
                    project=proj,
                    name=f"Late {j}",
                    target_date=AS_OF,
                    baseline_date=JAN,
                    status="at_risk",
                )
            )
            db.add(m.Milestone(project=proj, name=f"Early {j}", target_date=JAN, status="pending"))
        db.commit()
    return engine, factory


def _milestone_selects(engine: Engine, call: Callable[[], None]) -> int:
    """How many SELECTs touching the milestone table ``call`` runs."""
    counter = {"n": 0}

    def _bump(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        if "from milestone" in statement.lower():
            counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _bump)
    try:
        call()
    finally:
        event.remove(engine, "before_cursor_execute", _bump)
    return counter["n"]


def test_milestone_reads_batch_across_an_open_prefetch_scope() -> None:
    engine, factory = _milestone_store()
    with factory() as db:
        projects = list(db.scalars(select(m.Project).order_by(m.Project.name, m.Project.id)))

        def call() -> None:
            with adapters.prefetched(db, projects):
                for proj in projects:
                    for doc in _MILESTONE_DOCS:
                        doc.render(db, proj, AS_OF)

        selects = _milestone_selects(engine, call)
    assert selects <= 1, (
        f"{selects} milestone SELECTs for {N_PROJ} projects x {len(_MILESTONE_DOCS)} documents "
        "inside one prefetch scope (expected 1): a document is bypassing adapters.project_rows"
    )


def test_scoped_milestone_documents_render_the_same_bytes() -> None:
    """Scoped and scope-free renders are byte-identical, rows in the
    ``(target_date, id)`` order the per-document ORDER BY used to give."""
    _, factory = _milestone_store()
    with factory() as db:
        projects = list(db.scalars(select(m.Project).order_by(m.Project.name, m.Project.id)))
        singles = {
            (doc.SLUG, proj.id): doc.render(db, proj, AS_OF)
            for proj in projects
            for doc in _MILESTONE_DOCS
        }
    with factory() as db:
        projects = list(db.scalars(select(m.Project).order_by(m.Project.name, m.Project.id)))
        with adapters.prefetched(db, projects):
            for proj in projects:
                for doc in _MILESTONE_DOCS:
                    scoped = doc.render(db, proj, AS_OF)
                    assert scoped == singles[(doc.SLUG, proj.id)], (doc.SLUG, proj.name)
    sample = singles[(schedule.SLUG, projects[0].id)]
    assert sample.index("Early 0") < sample.index("Late 0")


def test_department_blended_rate_is_capacity_weighted(db: Session) -> None:
    """200/hr x 5h plus 50/hr x 40h supplies 45 hours costing 3000: 66.67/hr.
    The head-average printed 125.00."""
    business = m.Business(name="BRC")
    dept = m.Department(name="Delivery", business=business)
    dept.people.append(m.Person(name="Pat", role="specialist", cost_rate=200.0, capacity_hours=5.0))
    dept.people.append(m.Person(name="Sam", role="generalist", cost_rate=50.0, capacity_hours=40.0))
    db.add(dept)
    db.commit()

    row = department.department_rows(db, AS_OF)[0]
    assert row["blended_rate"] == "66.67", (
        f"blended_rate {row['blended_rate']}: the head-average is back"
    )
    assert row["capacity_hours"] == "45"
    assert "66.67" in department.render(db, AS_OF)
