"""``driftless.interchange.xer``: parse a Primavera XER file into an
``ImportedSchedule`` and write it through the CLI, same shape and proof as
``tests/test_interchange_msproject.py``.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import cli
from driftless.calc.network import (
    Activity,
    Dependency,
    ScheduleNetwork,
    backward_pass,
    critical_path,
    forward_pass,
)
from driftless.db import Base, new_engine, new_session_factory
from driftless.interchange.xer import parse_xer
from driftless.models import Business, Portfolio, Project

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "interchange" / "primavera-sample.xer"


def test_parse_xer_reads_tasks_and_dependencies() -> None:
    schedule = parse_xer(SAMPLE)
    names = {t.external_id: t.name for t in schedule.tasks}
    assert names == {"101": "Design", "102": "Build", "103": "Test", "104": "Docs"}
    durations = {t.external_id: t.duration_days for t in schedule.tasks}
    assert durations == {"101": 3, "102": 5, "103": 2, "104": 1}
    edges = {(d.predecessor, d.successor, d.kind) for d in schedule.dependencies}
    assert edges == {("101", "102", "FS"), ("102", "103", "FS")}


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


def test_import_xer_cli_writes_tasks_and_matches_critical_path(tmp_path: Path) -> None:
    url = _seed_db(tmp_path)
    rc = cli.main(["import", "xer", str(SAMPLE), "--project", "Migration", "--db-url", url])
    assert rc == 0

    engine = new_engine(url)
    session: Session = new_session_factory(engine)()
    try:
        project = session.scalar(select(Project).where(Project.name == "Migration"))
        assert project is not None
        by_name = {t.name: t for t in project.workstreams[0].tasks}
        assert set(by_name) == {"Design", "Build", "Test", "Docs"}

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
        early = forward_pass(network)
        late = backward_pass(network, early)
        paths = critical_path(network, early, late)
        expected = (str(by_name["Design"].id), str(by_name["Build"].id), str(by_name["Test"].id))
        assert paths == (expected,)
    finally:
        session.close()
