"""``capacity_hours`` is one person's capacity, not one project's slice of it.

The Resource evaluator used to sum a person's remaining hours *on this project*
and weigh that against their whole capacity, so a person could be at 150 % and
no project ever said so — the department page and the capacity heatmap printed
the true store-wide total (``person_task_loads``) beside the capacity in the
same row, and nothing compared them. These pin the repaired rule: the ratio is
store-wide, it is reported on every project that CONTRIBUTES hours to it (never
on one that does not), and the threat prints both halves so the figure
reconciles against the project's own board.
"""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from driftless.assess.evaluators import resource
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business, Person, Portfolio, Project, Task, Workstream

AS_OF = date(2026, 3, 31)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


@pytest.fixture
def store(session: Session) -> tuple[Project, Project, Person]:
    """Dana Ruiz from the demo seed: 40 h on one project, 20 h on another, 40 h
    of capacity. Neither project alone crosses the line; she does."""
    portfolio = Portfolio(name="Content", business=Business(name="BRC"))
    rollout = Project(name="Rollout", portfolio=portfolio, delivery_mode="predictive")
    archive = Project(name="Archive", portfolio=portfolio, delivery_mode="predictive")
    dana = Person(name="Dana Ruiz", capacity_hours=40.0)
    session.add_all(
        [
            Task(
                name="Rough cut",
                workstream=Workstream(name="Post", project=rollout),
                estimate_unit="hours",
                estimate=40.0,
                status="in_progress",
                assignee=dana,
            ),
            Task(
                name="Metadata pass",
                workstream=Workstream(name="Catalogue", project=archive),
                estimate_unit="hours",
                estimate=20.0,
                status="todo",
                assignee=dana,
            ),
        ]
    )
    session.commit()
    return rollout, archive, dana


def test_a_persons_load_is_weighed_across_every_project(
    session: Session, store: tuple[Project, Project, Person]
) -> None:
    """60 h against 40 h of capacity is red wherever those hours were booked."""
    rollout, archive, _ = store
    for project in (rollout, archive):
        assessment = resource.evaluate(session, project, AS_OF)
        assert assessment.status == "red", project.name
        assert "1.50" in assessment.threats[0].description, project.name


def test_the_threat_reconciles_the_total_with_this_projects_share(
    session: Session, store: tuple[Project, Project, Person]
) -> None:
    """A ratio the project's own board cannot reproduce reads as an error, so
    the threat prints the store-wide total AND the hours booked here."""
    rollout, archive, _ = store
    assert "60 h in all, 40 h of it on this project" in (
        resource.evaluate(session, rollout, AS_OF).threats[0].description
    )
    assert "60 h in all, 20 h of it on this project" in (
        resource.evaluate(session, archive, AS_OF).threats[0].description
    )


def test_a_project_holding_none_of_the_load_raises_nothing(
    session: Session, store: tuple[Project, Project, Person]
) -> None:
    """Reported on the projects that CAUSE the overload, not on every project in
    the store: a project Dana holds no open, hour-estimated work on stays green."""
    rollout, _, _ = store
    fleet = Project(name="Fleet", portfolio=rollout.portfolio, delivery_mode="predictive")
    session.add(Workstream(name="Rollout", project=fleet))
    session.commit()
    assert resource.evaluate(session, fleet, AS_OF).status == "green"
