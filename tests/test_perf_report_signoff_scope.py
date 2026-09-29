"""``report all`` must answer threat suppression from one ledger pass, not per threat.

``cli._render_all`` already opens ``adapters.prefetched`` + ``state.prefetched``
around the document loop, but ``state.prefetched``'s cache answers PROCESS
sign-offs only. The Assessment Report asks ``assess.is_suppressed`` once per
threat, and with no threat-ledger scope open every one of those fell through to
``state.latest_sign_off`` — a query per threat, so the bill grew with the store
(10 statements at 2 projects on this seed, 20 at 4, 40 at 8).
``engine.threat_sign_offs`` is the public scope for exactly that case; opened
alongside the other two it reads the THREAT ledger once for the whole run.

The counters here match statements rather than a total ceiling, so the guard
names the cost it is about: ``state.latest_sign_off`` is the only query in the
service that filters ``sign_off.subject_ref`` (grep it), and the scope's own pass
is the unfiltered ``subject_kind = 'threat'`` read. A probe test pins that the
counter really does see a scope-free check, so a zero can never be vacuous, and a
byte-equality test with a real suppressing sign-off in the store pins that the
scope changes where a decision is read from, never what it says.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from driftless import models as m
from driftless.assess import engine as assess_engine
from driftless.db import Base, new_engine, new_session_factory
from driftless.report import cli
from driftless.report import engine as report_engine
from driftless.report import receipt as report_receipt

AS_OF = date(2026, 6, 30)
JAN = date(2026, 1, 1)
TASKS_PER = 5


@dataclass
class _SignOffReads:
    """Sign-off statements a call ran, split by which path issued them."""

    per_threat: int  # state.latest_sign_off's fall-through: one query per threat
    ledger: int  # engine.threat_sign_offs' one pass over the THREAT ledger


def _populate(db: Session, projects: int) -> None:
    """A predictive store whose every project raises threats for the Assessment
    Report to run a suppression check against: an approved baseline, a milestone,
    a cost entry, a risk, and a department with a person."""
    business = m.Business(name="BRC")
    dept = m.Department(name="Delivery", business=business)
    dept.people.append(m.Person(name="Sam", role="editor", cost_rate=90.0))
    portfolio = m.Portfolio(name="Content Brands", business=business)
    for j in range(projects):
        proj = m.Project(
            name=f"Project {j:03d}",
            portfolio=portfolio,
            delivery_mode="predictive",
            responsible_department=dept,
        )
        ws = m.Workstream(name=f"WS{j}", project=proj)
        baseline = m.Baseline(project=proj, version=1, status="approved")
        for t in range(TASKS_PER):
            task = m.Task(
                name=f"T{j}.{t}",
                workstream=ws,
                estimate_unit="hours",
                percent_complete=(t * 20) % 100,
            )
            db.add(
                m.BaselineLine(
                    baseline=baseline,
                    task=task,
                    planned_start=JAN,
                    planned_finish=AS_OF,
                    planned_cost=1000.0,
                )
            )
        db.add(m.CostEntry(project=proj, category="labour", incurred_on=JAN, amount=300.0))
        db.add(
            m.Risk(
                project=proj,
                description=f"risk {j}",
                probability=0.5,
                impact=30000.0,
                status="open",
            )
        )
        db.add(
            m.Milestone(
                project=proj,
                name=f"M{j}",
                target_date=AS_OF,
                baseline_date=JAN,
                status="at_risk",
            )
        )
    db.commit()


def _store(projects: int) -> tuple[Engine, sessionmaker[Session]]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as db:
        _populate(db, projects)
    return engine, factory


def _count(
    engine: Engine, factory: sessionmaker[Session], call: Callable[[Session], Any]
) -> _SignOffReads:
    """Sign-off statements executed while ``call`` runs on a cold session."""
    reads = _SignOffReads(0, 0)

    def _seen(_c: Any, _u: Any, statement: str, parameters: Any, _x: Any, _m: Any) -> None:
        if "sign_off.subject_ref = " in statement:
            reads.per_threat += 1
        elif "sign_off.subject_kind = " in statement and "threat" in tuple(parameters):
            reads.ledger += 1

    with factory() as db:
        event.listen(engine, "before_cursor_execute", _seen)
        try:
            call(db)
        finally:
            event.remove(engine, "before_cursor_execute", _seen)
    return reads


def _worst_threat(db: Session, project: m.Project) -> Any:
    """The project's highest-scoring threat — the one a sign-off below suppresses."""
    threats = [t for a in assess_engine.assess_project(db, project, AS_OF) for t in a.threats]
    assert threats, "the seed must raise threats or a suppression guard proves nothing"
    return max(threats, key=lambda t: t.score)


def test_a_scope_free_suppression_check_is_one_per_threat_lookup() -> None:
    """The counter's own proof: outside any scope, one ``is_suppressed`` call is
    exactly one per-threat lookup — so a zero below means batched, not vacuous."""
    engine, factory = _store(1)
    with factory() as db:
        threat = _worst_threat(db, db.scalars(select(m.Project)).one())

    reads = _count(engine, factory, lambda db: assess_engine.is_suppressed(db, threat, AS_OF))
    assert reads == _SignOffReads(per_threat=1, ledger=0)


@pytest.mark.parametrize("projects", [2, 4, 8])
def test_render_all_reads_the_threat_ledger_once_however_many_projects(
    projects: int, tmp_path: Path
) -> None:
    """Suppression costs one ledger pass for the run, not one query per threat:
    the pre-fix path ran 10 per-threat lookups at 2 projects, 20 at 4 and 40 at 8,
    growing with the store; the scope is opened once, around the whole loop."""
    engine, factory = _store(projects)
    reads = _count(engine, factory, lambda db: cli._render_all(db, tmp_path, AS_OF))
    assert reads.per_threat == 0, (
        f"_render_all looked a threat sign-off up {reads.per_threat} times over {projects} "
        "projects: the document loop is running outside engine.threat_sign_offs again"
    )
    assert reads.ledger == 1, (
        f"_render_all made {reads.ledger} threat-ledger passes over {projects} projects: "
        "the scope must be opened once around the loop, not per project or per document"
    )


def test_the_scope_answers_a_real_sign_off_exactly_as_a_scope_free_render_does(
    tmp_path: Path,
) -> None:
    """A pure cost cut. With a suppressing THREAT sign-off in the store, every file
    the scoped loop writes stays byte-identical to the same document rendered alone
    on a scope-free session — the prefetched ledger and ``state.latest_sign_off``
    must reach the same decision. The unsigned bytes are pinned different, so this
    cannot pass because the sign-off did nothing."""
    _, factory = _store(2)
    with factory() as db:
        project = db.scalars(select(m.Project).order_by(m.Project.id)).first()
        assert project is not None
        worst, project_id, slug = _worst_threat(db, project), project.id, cli._slugify(project.name)
        cli._render_all(db, tmp_path / "unsigned", AS_OF)
    unsigned = (tmp_path / "unsigned" / AS_OF.isoformat() / slug / "assessment.md").read_text(
        encoding="utf-8"
    )

    with factory() as db:
        db.add(
            m.SignOff(
                project_id=project_id,
                subject_kind="threat",
                subject_ref=worst.id,
                decision="accepted",
                signal=worst.score,
                as_of=AS_OF,
            )
        )
        db.commit()
    with factory() as db:
        written = cli._render_all(db, tmp_path / "signed", AS_OF)
    assert written

    root = tmp_path / "signed" / AS_OF.isoformat()
    signed = (root / slug / "assessment.md").read_text(encoding="utf-8")
    assert signed != unsigned, "the sign-off must actually suppress, or the pin is vacuous"

    with factory() as db:
        projects = list(db.scalars(select(m.Project).order_by(m.Project.name, m.Project.id)))
        for module in report_engine.iter_documents():
            if getattr(module, "SCOPE", "project") == "business":
                path = root / f"{module.SLUG}.md"
                expected = report_receipt.attach_markdown_receipt(module.render(db, AS_OF), AS_OF)
                assert path.read_text(encoding="utf-8") == expected, module.SLUG
            else:
                for each in projects:
                    path = root / cli._slugify(each.name) / f"{module.SLUG}.md"
                    single = module.render(db, each, AS_OF)
                    expected = report_receipt.attach_markdown_receipt(single, AS_OF)
                    assert path.read_text(encoding="utf-8") == expected, (module.SLUG, each.name)
