"""Contract tests for the per-project RAID and money records.

The orphan-FK cases lean on the ``PRAGMA foreign_keys=ON`` listener in
``driftless.db.base`` — without it SQLite accepts every one and they prove nothing.
"""

from collections.abc import Callable, Iterator
from datetime import date
from typing import TypeVar

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from driftless.assess import exposure
from driftless.calc import evm
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import (
    Baseline,
    BudgetLine,
    Business,
    ChangeRequest,
    CostEntry,
    Issue,
    Portfolio,
    Project,
    Risk,
    Stakeholder,
    StatusSnapshot,
)
from driftless.models.records import OPEN_RISK_STATUSES
from driftless.report import gather
from driftless.report.documents import weekly_status

RAISED, LATER = date(2026, 1, 1), date(2026, 1, 10)
DEFAULTS: dict[type[Base], dict[str, object]] = {
    Risk: {"description": "Drone batteries slip", "probability": 0.4, "impact": 5000.0},
    Issue: {"description": "Colour grade rejected", "raised_on": RAISED},
    ChangeRequest: {"description": "Add a second edit pass", "raised_on": RAISED},
    BudgetLine: {"category": "labour", "planned_amount": 1000.0},
    CostEntry: {"category": "labour", "incurred_on": RAISED, "amount": 250.0},
    StatusSnapshot: {"taken_on": RAISED, "percent_complete": 40, "rag_status": "amber"},
    Stakeholder: {"name": "Sponsor"},
}
T = TypeVar("T", bound=Base)


def _row(model: type[T], **overrides: object) -> T:
    return model(**{**DEFAULTS[model], **overrides})


@pytest.fixture
def session() -> Iterator[Session]:
    """An in-memory SQLite session with the full schema created."""
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


@pytest.fixture
def project(session: Session) -> Project:
    """A committed project, ready to hang records off."""
    portfolio = Portfolio(name="Content Brands", business=Business(name="Back Road Creative"))
    project = Project(name="GoMoveShift 2026", portfolio=portfolio)
    session.add(project)
    session.commit()
    return project


def test_risk_exposure_is_derived_never_stored(session: Session, project: Project) -> None:
    session.add(_row(Risk, project=project, probability=0.4, impact=5000.0))
    session.commit()

    assert "exposure" not in Risk.__table__.columns, "exposure must not be a stored column"
    stored = session.get(Risk, 1)
    assert stored is not None
    assert stored.exposure == pytest.approx(2000.0)
    # The same expression compiles to SQL, so a filter cannot disagree with the property.
    assert session.scalars(select(Risk).where(Risk.exposure > 1999)).all() == [stored]
    assert session.scalars(select(Risk).where(Risk.exposure > 2001)).all() == []


def test_open_risk_statuses_is_one_shared_tuple() -> None:
    """``gather``, ``weekly_status`` and ``exposure`` all filter "open" risks
    through the SAME ``OPEN_RISK_STATUSES`` object from this module -- not
    three separately hand-typed ``("open", "mitigating")`` tuples that could
    quietly diverge again. ``exposure`` replaces ``adapters`` here because the
    open-risk *register* moved there wholesale; ``adapters`` no longer decides
    open-ness at all, so pinning it would pin nothing."""
    assert OPEN_RISK_STATUSES == ("open", "mitigating")
    assert gather.OPEN_RISKS is OPEN_RISK_STATUSES
    assert weekly_status.OPEN_RISK_STATUSES is OPEN_RISK_STATUSES
    assert exposure.OPEN_RISK_STATUSES is OPEN_RISK_STATUSES


def test_change_request_names_the_baseline_it_produced(session: Session, project: Project) -> None:
    superseded = Baseline(project=project, version=1, status="superseded")
    created = Baseline(project=project, version=2, status="approved")
    session.add(_row(ChangeRequest, project=project, status="approved", resulting_baseline=created))
    session.commit()

    stored = session.get(ChangeRequest, 1)
    assert stored is not None and stored.resulting_baseline is not None
    # The change produced a new version; the one it superseded is left intact, not edited.
    assert (stored.resulting_baseline.version, superseded.version) == (2, 1)


def test_planned_and_actual_share_the_cost_vocabulary(session: Session, project: Project) -> None:
    session.add(_row(BudgetLine, project=project))
    session.add(_row(CostEntry, project=project, amount=250.0))
    session.add(_row(CostEntry, project=project, amount=400.0, incurred_on=LATER))
    session.commit()

    line, entries = session.get(BudgetLine, 1), session.scalars(select(CostEntry)).all()
    assert line is not None and {entry.category for entry in entries} == {line.category}
    # The stored columns feed evm.actual_cost unchanged — same names, same meaning.
    costs = [evm.CostEntry(incurred_on=c.incurred_on, amount=c.amount) for c in entries]
    assert evm.actual_cost(costs, RAISED) == pytest.approx(250.0)


def test_one_budget_line_per_project_and_category(session: Session, project: Project) -> None:
    session.add_all([_row(BudgetLine, project=project), _row(BudgetLine, project=project)])
    with pytest.raises(IntegrityError):
        session.commit()


def test_one_status_snapshot_per_project_and_date(session: Session, project: Project) -> None:
    """The weekly series is append-only: two readings for one day cannot both stand."""
    session.add_all([_row(StatusSnapshot, project=project), _row(StatusSnapshot, project=project)])
    with pytest.raises(IntegrityError):
        session.commit()


def test_snapshots_trend_across_dates(session: Session, project: Project) -> None:
    session.add(_row(StatusSnapshot, project=project, percent_complete=40))
    session.add(_row(StatusSnapshot, project=project, taken_on=LATER, percent_complete=65))
    session.commit()

    series = session.scalars(select(StatusSnapshot).order_by(StatusSnapshot.taken_on)).all()
    assert [(s.taken_on, s.percent_complete) for s in series] == [(RAISED, 40), (LATER, 65)]


def test_issue_records_the_risk_it_came_from(session: Session, project: Project) -> None:
    realised = _row(Risk, project=project, status="realised")
    session.add_all(
        [
            _row(Issue, project=project, risk=realised),
            _row(Issue, project=project, description="Raised outright"),
        ]
    )
    session.commit()

    from_risk, outright = session.scalars(select(Issue).order_by(Issue.id)).all()
    assert from_risk.risk is not None and from_risk.risk.status == "realised"
    assert outright.risk_id is None  # an issue need not come from a logged risk


INVALID_ROWS: dict[str, Callable[[Project], object]] = {
    "orphan risk": lambda p: _row(Risk, project_id=999),
    "risk probability above one": lambda p: _row(Risk, project=p, probability=1.5),
    "risk probability negative": lambda p: _row(Risk, project=p, probability=-0.1),
    "risk impact negative": lambda p: _row(Risk, project=p, impact=-1.0),
    "risk status off-vocabulary": lambda p: _row(Risk, project=p, status="worrying"),
    "risk response off-vocabulary": lambda p: _row(Risk, project=p, response="panic"),
    "orphan issue": lambda p: _row(Issue, project_id=999),
    "issue status off-vocabulary": lambda p: _row(Issue, project=p, status="shrugged"),
    "issue resolved before raised": lambda p: _row(Issue, project=p, resolved_on=date(2025, 12, 1)),
    "orphan change request": lambda p: _row(ChangeRequest, project_id=999),
    "change status off-vocabulary": lambda p: _row(ChangeRequest, project=p, status="maybe"),
    "unapproved change names a baseline": lambda p: _row(
        ChangeRequest, project=p, resulting_baseline=Baseline(project=p, version=2)
    ),
    "orphan budget line": lambda p: _row(BudgetLine, project_id=999),
    "budget category off-vocabulary": lambda p: _row(BudgetLine, project=p, category="snacks"),
    "budget planned amount negative": lambda p: _row(BudgetLine, project=p, planned_amount=-1.0),
    "orphan cost entry": lambda p: _row(CostEntry, project_id=999),
    "cost category off-vocabulary": lambda p: _row(CostEntry, project=p, category="snacks"),
    "cost amount negative": lambda p: _row(CostEntry, project=p, amount=-1.0),
    "issue names a missing risk": lambda p: _row(Issue, project=p, risk_id=999),
    "orphan status snapshot": lambda p: _row(StatusSnapshot, project_id=999),
    "snapshot rag off-vocabulary": lambda p: _row(StatusSnapshot, project=p, rag_status="puce"),
    "snapshot percent above one hundred": lambda p: _row(
        StatusSnapshot, project=p, percent_complete=101
    ),
    "snapshot percent negative": lambda p: _row(StatusSnapshot, project=p, percent_complete=-1),
    "orphan stakeholder": lambda p: _row(Stakeholder, project_id=999),
    "stakeholder interest off-vocabulary": lambda p: _row(Stakeholder, project=p, interest="rabid"),
    "stakeholder influence off-vocabulary": lambda p: _row(
        Stakeholder, project=p, influence="total"
    ),
    "stakeholder cadence off-vocabulary": lambda p: _row(
        Stakeholder, project=p, comms_cadence="hourly"
    ),
}


@pytest.mark.parametrize("build", INVALID_ROWS.values(), ids=list(INVALID_ROWS))
def test_database_rejects_invalid_row(
    session: Session, project: Project, build: Callable[[Project], object]
) -> None:
    session.add(build(project))
    with pytest.raises(IntegrityError):
        session.commit()
