"""Green earned by judging rows, not by having none to judge.

``test_a_healthy_project_is_green_across_the_board`` runs every evaluator against
a bare project, so procurement, stakeholder and resource all answer green from
their EMPTY-collection early return — "nothing to assess" — and the populated
"has rows, none problematic" branch never executes anywhere in the suite. These
tests seed real, healthy rows so each judging predicate actually runs against
data and the verdict it returns — green, score 0.0, no threats, no actions — is
asserted. Rows exist in every case, so the empty early return cannot be the
branch that answered.
"""

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.assess.evaluators import procurement, resource, stakeholder
from driftless.assess.model import Assessment
from driftless.db import Base, new_engine, new_session_factory

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


@pytest.fixture
def project(session: Session) -> m.Project:
    project = m.Project(
        name="GMS",
        portfolio=m.Portfolio(name="Content", business=m.Business(name="BRC")),
        delivery_mode="predictive",
    )
    session.add(project)
    session.commit()
    return project


def _assert_clean_green(assessment: Assessment) -> None:
    """A judged-and-passed green: score 0.0, nothing raised, nothing recommended."""
    assert (assessment.status, assessment.risk_score) == ("green", 0.0)
    assert assessment.threats == ()
    assert assessment.actions == ()


def test_procurement_green_with_healthy_agreements_on_the_books(
    session: Session, project: m.Project
) -> None:
    """An active agreement inside its window and inside a real budget: every
    predicate — disputed, expired-active, over-budget — runs against rows and
    answers "fine". The budget line matters: without one the over-budget
    comparison is skipped rather than passed."""
    session.add(m.BudgetLine(project=project, category="services", planned_amount=10_000.0))
    session.add(
        m.ProcurementAgreement(
            project=project,
            vendor="DronesRUs",
            status="active",
            amount=5_000.0,
            start_date=JAN,
            end_date=AS_OF + timedelta(days=30),
        )
    )
    session.commit()
    _assert_clean_green(procurement.evaluate(session, project, AS_OF))


def test_stakeholder_green_when_no_power_player_is_disengaged(
    session: Session, project: m.Project
) -> None:
    """Registered stakeholders, none in the high-influence/low-interest quadrant:
    the grid filter runs over real rows and finds no gap. The high-influence,
    high-interest sponsor sits one attribute from the gap, so the filter must
    read both axes to pass her."""
    session.add_all(
        [
            m.Stakeholder(project=project, name="Sponsor", influence="high", interest="high"),
            m.Stakeholder(project=project, name="Neighbour", influence="low", interest="low"),
        ]
    )
    session.commit()
    _assert_clean_green(stakeholder.evaluate(session, project, AS_OF))


def test_resource_green_when_the_assignee_has_headroom(
    session: Session, project: m.Project
) -> None:
    """Real assigned work, comfortably inside capacity: 20 open hours against a
    40-hour capacity is a ratio of 0.5, computed and judged — under the 0.8
    amber line, so green with nothing raised."""
    session.add(
        m.Task(
            name="Grade",
            workstream=m.Workstream(name="Post", project=project),
            estimate_unit="hours",
            estimate=20.0,
            status="in_progress",
            assignee=m.Person(name="Sam", capacity_hours=40.0),
        )
    )
    session.commit()
    _assert_clean_green(resource.evaluate(session, project, AS_OF))
