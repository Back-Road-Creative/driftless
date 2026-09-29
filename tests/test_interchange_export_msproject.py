"""``driftless export msproject``: write the approved baseline back out as MSPDI
XML, and prove it round-trips — the existing importer reads the export back
into a fresh store with the same critical path, and exporting twice writes
identical bytes.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from driftless import cli
from driftless import models as m
from driftless.calc.network import (
    Activity,
    Dependency,
    ScheduleNetwork,
    backward_pass,
    critical_path,
    forward_pass,
)
from driftless.db import Base, new_engine, new_session_factory
from driftless.interchange.common import write_imported_schedule
from driftless.interchange.msproject import export_msproject_xml, parse_msproject_xml
from driftless.pmbok.schedule_facts import schedule_facts

JAN = date(2026, 1, 1)
AS_OF = date(2026, 3, 31)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'export.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


def _seed_baselined_project(db: Session) -> m.Project:
    """Design -> Build -> Test chained, Docs parallel and off the critical path
    — the same shape ``tests/fixtures/interchange/msproject-sample.xml`` uses for
    import."""
    portfolio = m.Portfolio(name="Content", business=m.Business(name="BRC"))
    project = m.Project(name="Migration", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="Delivery", project=project)
    design = m.Task(name="Design", workstream=stream, estimate_unit="hours")
    build = m.Task(name="Build", workstream=stream, estimate_unit="hours")
    test = m.Task(name="Test", workstream=stream, estimate_unit="hours")
    docs = m.Task(name="Docs", workstream=stream, estimate_unit="hours")
    baseline = m.Baseline(project=project, version=1, status="approved", approved_at=JAN)
    db.add_all(
        [
            m.BaselineLine(
                baseline=baseline,
                task=design,
                planned_cost=300.0,
                planned_start=JAN,
                planned_finish=JAN + timedelta(days=3),
            ),
            m.BaselineLine(
                baseline=baseline,
                task=build,
                planned_cost=500.0,
                planned_start=JAN + timedelta(days=3),
                planned_finish=JAN + timedelta(days=8),
            ),
            m.BaselineLine(
                baseline=baseline,
                task=test,
                planned_cost=200.0,
                planned_start=JAN + timedelta(days=8),
                planned_finish=JAN + timedelta(days=10),
            ),
            m.BaselineLine(
                baseline=baseline,
                task=docs,
                planned_cost=100.0,
                planned_start=JAN,
                planned_finish=JAN + timedelta(days=1),
            ),
        ]
    )
    db.commit()
    db.add(m.TaskDependency(predecessor=design, successor=build, kind="FS"))
    db.add(m.TaskDependency(predecessor=build, successor=test, kind="FS"))
    db.commit()
    return project


def test_export_writes_the_approved_baseline_as_mspdi(db: Session) -> None:
    project = _seed_baselined_project(db)
    facts = schedule_facts(db, project, AS_OF)
    assert facts is not None
    xml_bytes = export_msproject_xml(facts)
    assert xml_bytes.startswith(b"<?xml")
    assert b"http://schemas.microsoft.com/project" in xml_bytes


def test_exporting_twice_is_byte_identical(db: Session) -> None:
    project = _seed_baselined_project(db)
    facts = schedule_facts(db, project, AS_OF)
    assert facts is not None
    assert export_msproject_xml(facts) == export_msproject_xml(facts)


def test_export_round_trips_through_the_importer_with_the_same_critical_path(
    db: Session, tmp_path: Path
) -> None:
    project = _seed_baselined_project(db)
    facts = schedule_facts(db, project, AS_OF)
    assert facts is not None

    exported = tmp_path / "roundtrip.xml"
    exported.write_bytes(export_msproject_xml(facts))

    schedule = parse_msproject_xml(exported)
    fresh_url = f"sqlite:///{tmp_path / 'reimport.db'}"
    fresh_engine = new_engine(fresh_url)
    Base.metadata.create_all(fresh_engine)
    with new_session_factory(fresh_engine)() as fresh_db:
        fresh_project = m.Project(
            name="Migration Reimport",
            portfolio=m.Portfolio(name="Content", business=m.Business(name="BRC")),
        )
        fresh_db.add(fresh_project)
        fresh_db.commit()
        tasks = write_imported_schedule(
            fresh_db, fresh_project, schedule, workstream_name="Reimported"
        )
        fresh_db.commit()

        names_by_id = {str(task.id): task.name for task in tasks.values()}
        activities = tuple(
            Activity(id=str(task.id), duration=int(task.estimate or 0)) for task in tasks.values()
        )
        deps = tuple(
            Dependency(
                predecessor=str(tasks[dep.predecessor].id),
                successor=str(tasks[dep.successor].id),
                kind=dep.kind,
            )
            for dep in schedule.dependencies
        )
        reimported_network = ScheduleNetwork(activities=activities, dependencies=deps)
        reimported_early = forward_pass(reimported_network)
        reimported_late = backward_pass(reimported_network, reimported_early)
        reimported_path = critical_path(reimported_network, reimported_early, reimported_late)
        reimported_critical_names = {names_by_id[aid] for path in reimported_path for aid in path}

    original_early = forward_pass(facts.network)
    original_late = backward_pass(facts.network, original_early)
    original_path = critical_path(facts.network, original_early, original_late)
    original_names = {facts.task_names[aid] for path in original_path for aid in path}

    # both critical paths name the same tasks, even though the ids differ
    # between the original store and the freshly reimported one
    assert original_names == reimported_critical_names == {"Design", "Build", "Test"}


def test_export_cli_writes_mspdi_to_stdout(
    db: Session, tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    url = f"sqlite:///{tmp_path / 'cli-export.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        _seed_baselined_project(session)

    rc = cli.main(
        [
            "export",
            "msproject",
            "--project",
            "Migration",
            "--as-of",
            AS_OF.isoformat(),
            "--db-url",
            url,
        ]
    )
    assert rc == 0
    captured = capsysbinary.readouterr()
    assert captured.out.startswith(b"<?xml")


def test_export_cli_reports_unknown_project(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'no-project.db'}"
    Base.metadata.create_all(new_engine(url))
    rc = cli.main(["export", "msproject", "--project", "Nonexistent", "--db-url", url])
    assert rc == 2


def test_export_cli_reports_no_approved_baseline(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'empty.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        session.add(
            m.Project(
                name="Bare",
                portfolio=m.Portfolio(name="Content", business=m.Business(name="BRC")),
            )
        )
        session.commit()

    rc = cli.main(["export", "msproject", "--project", "Bare", "--db-url", url])
    assert rc == 2
