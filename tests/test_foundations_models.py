"""Contract tests for the PR-1 foundation models: org, sign-off and the
narrative / quality / procurement records that make the last knowledge areas real.

The orphan-FK cases lean on the ``PRAGMA foreign_keys=ON`` listener in
``driftless.db.base`` — without it SQLite accepts every one and they prove nothing.
"""

from collections.abc import Callable, Iterator
from datetime import date, timedelta
from typing import TypeVar

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from driftless.db import Base, new_engine, new_session_factory
from driftless.models import (
    Business,
    Department,
    NarrativeArtifact,
    Person,
    Portfolio,
    ProcurementAgreement,
    Project,
    QualityMeasurement,
    SignOff,
    Task,
    Workstream,
)

START, END = date(2026, 1, 1), date(2026, 6, 30)
T = TypeVar("T", bound=Base)


@pytest.fixture
def session() -> Iterator[Session]:
    """An in-memory SQLite session with the full schema created."""
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


@pytest.fixture
def business(session: Session) -> Business:
    business = Business(name="Back Road Creative")
    session.add(business)
    session.commit()
    return business


@pytest.fixture
def project(session: Session, business: Business) -> Project:
    portfolio = Portfolio(name="Content Brands", business=business)
    project = Project(name="GoMoveShift 2026", portfolio=portfolio)
    session.add(project)
    session.commit()
    return project


def test_department_and_person_round_trip(session: Session, business: Business) -> None:
    editing = Department(business=business, name="Editing")
    session.add(Person(name="Alex", department=editing, role="editor", cost_rate=85.0))
    session.commit()

    person = session.scalars(select(Person)).one()
    assert person.department is not None and person.department.name == "Editing"
    assert person.cost_rate == pytest.approx(85.0)
    assert person.capacity_hours == pytest.approx(40.0)  # the default the resource maths uses
    # Read-only mirror: the department lists its people.
    assert [p.name for p in editing.people] == ["Alex"]


def test_task_assignee_is_writable_and_person_tasks_mirrors_it(
    session: Session, project: Project
) -> None:
    person = Person(name="Sam")
    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours", assignee=person)
    session.add(task)
    session.commit()

    stored = session.scalars(select(Task)).one()
    assert stored.assignee is not None and stored.assignee.name == "Sam"
    # ``Person.tasks`` is the read-only side of the same FK — one owner, no drift.
    assert [t.name for t in person.tasks] == ["Grade"]


def test_task_records_actual_and_forecast_finish(session: Session, project: Project) -> None:
    stream = Workstream(name="Post", project=project)
    task = Task(
        name="Grade",
        workstream=stream,
        estimate_unit="hours",
        actual_finish=date(2026, 6, 15),
        forecast_finish=date(2026, 6, 20),
    )
    session.add(task)
    session.commit()

    stored = session.scalars(select(Task)).one()
    assert stored.actual_finish == date(2026, 6, 15)
    assert stored.forecast_finish == date(2026, 6, 20)


def test_task_actual_and_forecast_finish_default_to_null(
    session: Session, project: Project
) -> None:
    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours")
    session.add(task)
    session.commit()

    stored = session.scalars(select(Task)).one()
    assert stored.actual_finish is None
    assert stored.forecast_finish is None


def test_project_names_a_responsible_department(session: Session, project: Project) -> None:
    delivery = Department(business=project.portfolio.business, name="Delivery")
    project.responsible_department = delivery
    session.commit()

    stored = session.get(Project, project.id)
    assert stored is not None and stored.responsible_department is not None
    assert stored.responsible_department.name == "Delivery"


def test_sign_off_ledger_is_append_only_and_orders_by_time(
    session: Session, project: Project
) -> None:
    """Two decisions on one subject coexist; the latest is simply the last row."""
    first = SignOff(
        project=project,
        subject_kind="threat",
        subject_ref="cost:project:1",
        decision="deferred",
        signal=1.5,
        signed_by="jp",
        as_of=START,
    )
    session.add(first)
    session.commit()
    later = SignOff(
        project=project,
        subject_kind="threat",
        subject_ref="cost:project:1",
        decision="rejected",
        signal=1.5,
        signed_by="jp",
        as_of=END,
    )
    session.add(later)
    session.commit()

    ledger = session.scalars(select(SignOff).order_by(SignOff.signed_at, SignOff.id)).all()
    assert [s.decision for s in ledger] == ["deferred", "rejected"]
    assert ledger[-1].signed_at is not None  # stamped at the write boundary


def test_narrative_artifact_is_one_per_project_and_kind(session: Session, project: Project) -> None:
    session.add_all(
        [
            NarrativeArtifact(project=project, kind="assumption_log", body="a"),
            NarrativeArtifact(project=project, kind="assumption_log", body="b"),
        ]
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_quality_metric_may_be_read_many_times(session: Session, project: Project) -> None:
    """A metric trends: two readings on different dates both stand — no uniqueness."""
    session.add_all(
        [
            QualityMeasurement(
                project=project,
                metric="defect_rate",
                target_value=1.0,
                actual_value=3.0,
                measured_on=START,
            ),
            QualityMeasurement(
                project=project,
                metric="defect_rate",
                target_value=1.0,
                actual_value=1.5,
                measured_on=END,
            ),
        ]
    )
    session.commit()
    series = session.scalars(
        select(QualityMeasurement).order_by(QualityMeasurement.measured_on)
    ).all()
    assert [m.actual_value for m in series] == [3.0, 1.5]


def test_procurement_agreement_round_trips(session: Session, project: Project) -> None:
    session.add(
        ProcurementAgreement(
            project=project,
            vendor="DronesRUs",
            amount=12000.0,
            status="active",
            start_date=START,
            end_date=END,
        )
    )
    session.commit()
    stored = session.scalars(select(ProcurementAgreement)).one()
    assert stored.vendor == "DronesRUs" and stored.status == "active"


def _department(project: Project, **overrides: object) -> Department:
    return Department(**{"business": project.portfolio.business, "name": "Ops", **overrides})


INVALID_ROWS: dict[str, Callable[[Project], object]] = {
    "orphan department": lambda p: Department(business_id=999, name="Ghost"),
    "person cost rate negative": lambda p: Person(name="X", cost_rate=-1.0),
    "person capacity zero": lambda p: Person(name="X", capacity_hours=0.0),
    "person capacity negative": lambda p: Person(name="X", capacity_hours=-1.0),
    "orphan person department": lambda p: Person(name="X", department_id=999),
    "orphan task assignee": lambda p: Task(
        name="T", workstream=Workstream(name="W", project=p), assignee_id=999
    ),
    "orphan project department": lambda p: _project_with_department(p, 999),
    "signoff subject off-vocabulary": lambda p: SignOff(
        project=p, subject_kind="wibble", subject_ref="x", decision="accepted"
    ),
    "signoff decision off-vocabulary": lambda p: SignOff(
        project=p, subject_kind="threat", subject_ref="x", decision="shrugged"
    ),
    "orphan signoff project": lambda p: SignOff(
        project_id=999, subject_kind="threat", subject_ref="x", decision="accepted"
    ),
    "narrative kind off-vocabulary": lambda p: NarrativeArtifact(project=p, kind="diary"),
    "orphan narrative project": lambda p: NarrativeArtifact(project_id=999, kind="eef"),
    "orphan quality project": lambda p: QualityMeasurement(
        project_id=999, metric="m", target_value=1.0, actual_value=1.0, measured_on=START
    ),
    "orphan procurement project": lambda p: ProcurementAgreement(
        project_id=999, vendor="V", start_date=START
    ),
    "procurement status off-vocabulary": lambda p: ProcurementAgreement(
        project=p, vendor="V", status="pending", start_date=START
    ),
    "procurement amount negative": lambda p: ProcurementAgreement(
        project=p, vendor="V", amount=-1.0, start_date=START
    ),
    "procurement end before start": lambda p: ProcurementAgreement(
        project=p, vendor="V", start_date=END, end_date=START
    ),
}


def _project_with_department(project: Project, department_id: int) -> Project:
    project.responsible_department_id = department_id
    return project


@pytest.mark.parametrize("build", INVALID_ROWS.values(), ids=list(INVALID_ROWS))
def test_database_rejects_invalid_row(
    session: Session, project: Project, build: Callable[[Project], object]
) -> None:
    session.add(build(project))
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_department_name_in_one_business_is_refused(
    session: Session, project: Project
) -> None:
    session.add_all([_department(project), _department(project)])
    with pytest.raises(IntegrityError):
        session.commit()


def test_same_department_name_across_businesses_is_allowed(session: Session) -> None:
    one = Business(name="Alpha")
    two = Business(name="Beta")
    session.add_all([Department(business=one, name="Ops"), Department(business=two, name="Ops")])
    session.commit()
    assert len(session.scalars(select(Department)).all()) == 2


def test_open_ended_agreement_needs_no_end_date(session: Session, project: Project) -> None:
    session.add(ProcurementAgreement(project=project, vendor="Retainer Co", start_date=START))
    session.commit()
    assert session.scalars(select(ProcurementAgreement)).one().end_date is None


assert END - START > timedelta(days=0)  # the fixtures assume a forward window
