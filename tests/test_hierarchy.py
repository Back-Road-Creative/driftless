"""Contract tests for the hierarchy models and the SQLite foreign-key pragma.

The FK tests are the important ones: SQLite ships with foreign-key enforcement
OFF, so without the ``PRAGMA foreign_keys=ON`` listener in ``driftless.db.base``
every FK in this schema would be documentation rather than a constraint, and
these tests would pass while proving nothing.
"""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from driftless.db import Base, new_engine, new_session_factory
from driftless.models import (
    Baseline,
    Business,
    Milestone,
    Portfolio,
    Program,
    Project,
    Sprint,
    Task,
    Workstream,
)


@pytest.fixture
def session() -> Iterator[Session]:
    """An in-memory SQLite session with the full schema created."""
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


def _project(session: Session, *, grouped: bool) -> Project:
    business = Business(name="Back Road Creative")
    portfolio = Portfolio(name="Content Brands", business=business)
    program = Program(name="Video", portfolio=portfolio) if grouped else None
    project = Project(
        name="GoMoveShift 2026",
        delivery_mode="agile",
        portfolio=portfolio,
        program=program,
    )
    session.add(project)
    session.commit()
    return project


def test_full_chain_persists(session: Session) -> None:
    project = _project(session, grouped=True)
    workstream = Workstream(name="Editing", project=project)
    session.add(Task(name="Cut the trailer", workstream=workstream, estimate=5))
    session.commit()

    stored = session.get(Task, 1)
    assert stored is not None
    assert stored.workstream.project.program is not None
    assert stored.workstream.project.program.portfolio.business.name == "Back Road Creative"
    assert stored.estimate_unit == "points"
    assert stored.percent_complete == 0


def test_program_is_optional_so_a_project_can_hang_off_a_portfolio(session: Session) -> None:
    project = _project(session, grouped=False)
    assert project.program_id is None
    assert project.portfolio.name == "Content Brands"


def test_project_navigates_to_its_delivery_records(session: Session) -> None:
    """Parent -> child navigation, so a caller never hand-writes a ``select()`` for these."""
    project = _project(session, grouped=False)
    session.add_all(
        [
            Baseline(project=project, version=1, status="superseded"),
            Baseline(project=project, version=2, status="approved"),
            Milestone(project=project, name="Season one live", target_date=date(2026, 1, 10)),
            Sprint(
                project=project,
                name="Sprint 1",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 10),
            ),
        ]
    )
    session.commit()

    stored = session.get(Project, project.id)
    assert stored is not None
    assert sorted(baseline.version for baseline in stored.baselines) == [1, 2]
    assert [milestone.name for milestone in stored.milestones] == ["Season one live"]
    assert [sprint.name for sprint in stored.sprints] == ["Sprint 1"]


def test_orphan_portfolio_raises_integrity_error(session: Session) -> None:
    """Proof the pragma listener is live: without it SQLite accepts this row."""
    session.add(Portfolio(name="Orphan", business_id=999))
    with pytest.raises(IntegrityError):
        session.commit()


def test_orphan_task_raises_integrity_error(session: Session) -> None:
    session.add(Task(name="Orphan", workstream_id=999))
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize("mode", ["waterfall", ""])
def test_delivery_mode_is_constrained(session: Session, mode: str) -> None:
    business = Business(name="BRC")
    portfolio = Portfolio(name="Client Work", business=business)
    session.add(Project(name="Bad mode", delivery_mode=mode, portfolio=portfolio))
    with pytest.raises(IntegrityError):
        session.commit()


def test_estimate_unit_is_constrained(session: Session) -> None:
    project = _project(session, grouped=False)
    workstream = Workstream(name="Editing", project=project)
    session.add(Task(name="Bad unit", workstream=workstream, estimate_unit="bananas"))
    with pytest.raises(IntegrityError):
        session.commit()
