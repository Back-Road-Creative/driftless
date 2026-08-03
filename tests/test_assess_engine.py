"""The assessment engine: evaluators → threats, Integration roll-up, sign-off suppression.

The cost evaluator is the worked example (the other eight are exercised in their
own tests). What is pinned here is the engine's own behaviour: it assesses all
ten knowledge areas, Integration is the worst-of its children, a sign-off hides a
threat only while the situation is no worse than at sign-off (a regression brings
it back), and the whole thing regenerates byte-identically.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from driftless.assess import engine
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import (
    Baseline,
    BaselineLine,
    Business,
    CostEntry,
    Portfolio,
    Project,
    SignOff,
    Task,
    Workstream,
)

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)


@pytest.fixture
def session() -> Iterator[Session]:
    engine_ = new_engine("sqlite://")
    Base.metadata.create_all(engine_)
    with new_session_factory(engine_)() as db:
        yield db


@pytest.fixture
def project(session: Session) -> Project:
    """A project overspending badly: BAC 1000, EV 200 (20% done), AC 800 -> CPI 0.25 (red)."""
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = Baseline(project=project, version=1, status="approved")
    line = BaselineLine(
        baseline=baseline, task=task, planned_cost=1000.0, planned_start=JAN, planned_finish=AS_OF
    )
    session.add(line)
    session.add(CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    session.commit()
    return project


def _cost_threat(session: Session, project: Project) -> object:
    return next(t for t in engine.live_threats(session, project, AS_OF) if t.kind == "cost")


def test_assess_project_covers_all_ten_knowledge_areas(session: Session, project: Project) -> None:
    assessments = engine.assess_project(session, project, AS_OF)
    kinds = {a.kind for a in assessments}
    assert len(assessments) == 10
    assert kinds == {
        "integration",
        "scope",
        "schedule",
        "cost",
        "quality",
        "resource",
        "communications",
        "risk",
        "procurement",
        "stakeholder",
    }


def test_cost_is_red_and_integration_rolls_it_up(session: Session, project: Project) -> None:
    by_kind = {a.kind: a for a in engine.assess_project(session, project, AS_OF)}
    assert by_kind["cost"].status == "red" and by_kind["cost"].threats
    assert by_kind["cost"].actions, "a red assessment recommends actions"
    # Integration is worst-of; with cost red it must be red too.
    assert by_kind["integration"].status == "red"
    assert by_kind["scope"].status == "green"  # a stubbed area stays green


def test_a_sign_off_suppresses_a_threat_until_it_regresses(
    session: Session, project: Project
) -> None:
    threat = _cost_threat(session, project)
    assert threat.severity == "red"

    # Sign it off at its current score -> gone from the live feed.
    session.add(
        SignOff(
            project=project,
            subject_kind="threat",
            subject_ref=threat.id,
            decision="accepted",
            signal=threat.score,
        )
    )
    session.commit()
    assert engine.is_suppressed(session, threat, AS_OF)
    assert all(t.kind != "cost" for t in engine.live_threats(session, project, AS_OF))

    # Regress: more spend -> CPI drops -> the cost score climbs past the signed level.
    session.add(CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    session.commit()
    worse = _cost_threat(session, project)
    assert worse.score > threat.score, "the regression raised the score"
    assert not engine.is_suppressed(session, worse, AS_OF), "a regression re-surfaces the threat"


def test_a_sign_off_without_a_signal_never_suppresses(session: Session, project: Project) -> None:
    threat = _cost_threat(session, project)
    session.add(
        SignOff(
            project=project,
            subject_kind="threat",
            subject_ref=threat.id,
            decision="accepted",
            signal=None,
        )
    )
    session.commit()
    assert not engine.is_suppressed(session, threat, AS_OF)


def test_the_latest_sign_off_wins_for_a_threat(session: Session, project: Project) -> None:
    threat = _cost_threat(session, project)
    session.add_all(
        [
            SignOff(
                project=project,
                subject_kind="threat",
                subject_ref=threat.id,
                decision="accepted",
                signal=threat.score,
                signed_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            SignOff(
                project=project,
                subject_kind="threat",
                subject_ref=threat.id,
                decision="rejected",
                signal=threat.score,
                signed_at=datetime(2026, 2, 1, tzinfo=UTC),
            ),
        ]
    )
    session.commit()
    assert not engine.is_suppressed(session, threat, AS_OF), "a later rejection un-suppresses"


def test_top_threats_ranks_across_the_store(session: Session, project: Project) -> None:
    threats = engine.top_threats(session, AS_OF)
    assert threats, "the overspending project raises threats"
    weights = [engine.SEVERITY_WEIGHT[t.severity] for t in threats]
    assert weights == sorted(weights, reverse=True), "most severe first"


def test_assessment_regenerates_identically(session: Session, project: Project) -> None:
    def snapshot() -> list[tuple[str, str, float]]:
        return [
            (a.kind, a.status, a.risk_score) for a in engine.assess_project(session, project, AS_OF)
        ]

    assert snapshot() == snapshot()
