"""``driftless.interchange.msproject``: parse an MSPDI file into an
``ImportedSchedule``, write it through the CLI, and prove the critical path
``calc.network`` computes over the imported rows matches the sample's known
path (Design -> Build -> Test; Docs is parallel and off the critical path).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import cli
from driftless.calc.network import Activity, Dependency, ScheduleNetwork, critical_path
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import ChangeLog
from driftless.interchange.msproject import parse_msproject_xml
from driftless.models import Business, Portfolio, Project

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "interchange" / "msproject-sample.xml"


def test_parse_msproject_xml_reads_tasks_and_dependencies() -> None:
    schedule = parse_msproject_xml(SAMPLE)
    names = {t.external_id: t.name for t in schedule.tasks}
    assert names == {"1": "Design", "2": "Build", "3": "Test", "4": "Docs"}
    durations = {t.external_id: t.duration_days for t in schedule.tasks}
    assert durations == {"1": 3, "2": 5, "3": 2, "4": 1}
    edges = {(d.predecessor, d.successor, d.kind) for d in schedule.dependencies}
    assert edges == {("1", "2", "FS"), ("2", "3", "FS")}


def _seed_db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        session.add(
            Project(name="Migration", portfolio=Portfolio(name="P", business=Business(name="B")))
        )
        session.commit()
    return url


def test_import_msproject_cli_writes_tasks_dependencies_and_critical_path(tmp_path: Path) -> None:
    url = _seed_db(tmp_path)
    rc = cli.main(["import", "msproject", str(SAMPLE), "--project", "Migration", "--db-url", url])
    assert rc == 0

    engine = new_engine(url)
    session: Session = new_session_factory(engine)()
    try:
        project = session.scalar(select(Project).where(Project.name == "Migration"))
        assert project is not None
        by_name = {t.name: t for t in project.workstreams[0].tasks}
        assert set(by_name) == {"Design", "Build", "Test", "Docs"}

        # every write landed in the append-only ChangeLog, same as an API write
        change_rows = session.scalars(select(ChangeLog).where(ChangeLog.table_name == "task")).all()
        assert len(change_rows) == 4
        assert all(row.operation == "insert" for row in change_rows)

        activities = tuple(
            Activity(id=str(task.id), duration=int(task.estimate or 0)) for task in by_name.values()
        )
        dependencies = (
            Dependency(
                predecessor=str(by_name["Design"].id),
                successor=str(by_name["Build"].id),
                kind="FS",
            ),
            Dependency(
                predecessor=str(by_name["Build"].id),
                successor=str(by_name["Test"].id),
                kind="FS",
            ),
        )
        network = ScheduleNetwork(activities=activities, dependencies=dependencies)
        from driftless.calc.network import backward_pass, forward_pass

        early = forward_pass(network)
        late = backward_pass(network, early)
        paths = critical_path(network, early, late)
        expected = (str(by_name["Design"].id), str(by_name["Build"].id), str(by_name["Test"].id))
        assert paths == (expected,)
    finally:
        session.close()
