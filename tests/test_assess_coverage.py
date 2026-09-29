"""Coverage is a separate fact from an assessment's RAG state.

The assessment engine historically used green both for healthy evidence and for
areas without anything recorded.  The balanced operating view needs to distinguish
those answers without perturbing the threat/ranking contract.
"""

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from driftless.assess import engine
from driftless.assess.model import Assessment
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import (
    Baseline,
    BaselineLine,
    Business,
    Portfolio,
    Project,
    QualityMeasurement,
    Stakeholder,
    StatusSnapshot,
    Task,
    Workstream,
)

AS_OF = date(2026, 3, 31)
JAN = date(2026, 1, 1)


@pytest.fixture
def session() -> Iterator[Session]:
    db_engine = new_engine("sqlite://")
    Base.metadata.create_all(db_engine)
    with new_session_factory(db_engine)() as db:
        yield db


@pytest.fixture
def project(session: Session) -> Project:
    row = Project(name="GMS", portfolio=Portfolio(name="Content", business=Business(name="BRC")))
    session.add(row)
    session.commit()
    return row


def test_assessments_distinguish_missing_stale_measured_and_not_applicable(
    session: Session, project: Project
) -> None:
    """Coverage reports evidence state independently from the RAG verdict."""
    session.add(
        QualityMeasurement(
            project=project,
            metric="defects",
            target_value=1.0,
            actual_value=0.5,
            measured_on=AS_OF - timedelta(days=90),
        )
    )
    session.add(StatusSnapshot(project=project, taken_on=AS_OF, rag_status="green"))
    session.commit()

    by_kind = {
        assessment.kind: assessment for assessment in engine.assess_project(session, project, AS_OF)
    }

    assert by_kind["quality"].status == "amber"
    assert by_kind["quality"].coverage == "stale"
    assert by_kind["communications"].status == "green"
    assert by_kind["communications"].coverage == "measured"
    assert by_kind["stakeholder"].status == "green"
    assert by_kind["stakeholder"].coverage == "missing"
    assert by_kind["procurement"].status == "green"
    assert by_kind["procurement"].coverage == "not_applicable"


def test_integration_coverage_reports_a_missing_child_area(
    session: Session, project: Project
) -> None:
    """A green integration roll-up cannot hide missing delivery evidence."""
    integration = engine.assess_project(session, project, AS_OF)[0]

    assert integration.kind == "integration"
    assert integration.status == "amber"
    assert integration.coverage == "missing"


def test_integration_coverage_reports_stale_when_nothing_is_missing(
    session: Session, project: Project
) -> None:
    """No child area is ``missing``, but one is ``stale`` — the elif rung between
    the ``missing`` roll-up above and the ``measured``/``not_applicable`` pair
    below, reached only when every evaluator that CAN be missing is not."""
    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = Baseline(project=project, version=1, status="approved")
    session.add(
        BaselineLine(
            baseline=baseline,
            task=task,
            planned_cost=1000.0,
            planned_start=JAN,
            planned_finish=AS_OF,
        )
    )
    session.add(Stakeholder(project=project, name="Ada", interest="high", influence="high"))
    session.add(StatusSnapshot(project=project, taken_on=AS_OF, rag_status="green"))
    session.add(
        QualityMeasurement(
            project=project,
            metric="defects",
            target_value=1.0,
            actual_value=0.5,
            measured_on=AS_OF - timedelta(days=90),
        )
    )
    session.commit()

    by_kind = {
        assessment.kind: assessment for assessment in engine.assess_project(session, project, AS_OF)
    }
    assert by_kind["cost"].coverage == "measured", "the baseline must keep cost off 'missing'"
    assert by_kind["stakeholder"].coverage != "missing", "a registered stakeholder is not 'missing'"
    assert not any(a.coverage == "missing" for a in by_kind.values() if a.kind != "integration")
    assert any(a.coverage == "stale" for a in by_kind.values())

    integration = by_kind["integration"]
    assert integration.coverage == "stale"


def test_integration_coverage_falls_back_to_not_applicable(session: Session) -> None:
    """The final ``else`` — reached only when NONE of the nine areas is
    ``missing``, ``stale`` or ``measured``. No live evaluator combination can
    do this (schedule, resource, scope and risk always default to
    ``measured``), so this drives the roll-up directly with a synthetic
    tuple, the same way a private helper with no public path to one branch
    is tested anywhere else in this suite."""
    nine = tuple(
        Assessment(kind, AS_OF, 0.0, "green", coverage="not_applicable")
        for kind in (
            "scope",
            "schedule",
            "cost",
            "quality",
            "resource",
            "communications",
            "risk",
            "procurement",
            "stakeholder",
        )
    )
    project = Project(name="Synthetic", portfolio=Portfolio(name="X", business=Business(name="Y")))
    integration = engine._integration(nine, project, AS_OF)
    assert integration.coverage == "not_applicable"
