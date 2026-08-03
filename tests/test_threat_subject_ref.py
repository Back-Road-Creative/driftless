"""One builder for every threat sign-off subject_ref — and the suppression round-trip it guards.

``threat_subject_ref`` is the single place the ``"{kind}:project:{id}"`` convention
lives, mirroring ``process_subject_ref`` for the process side. Every evaluator's
``Threat.id`` is this ref, so ``engine.is_suppressed`` (which looks a threat up by
``threat.id`` under byte equality) suppresses exactly the threat a sign-off names.
The feed prepends a ``"threat:"`` display prefix to that ref for its item id; the
web strips it back to recover the subject_ref, so the whole round-trip has to agree
on one canonical form. These tests pin the format and prove the round-trip per kind.
"""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from driftless.assess import engine, feed
from driftless.assess.model import Threat
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
from driftless.pmbok.state import threat_subject_ref

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)

#: The ten threat kinds that carry a "threat" sign-off subject (nine areas + the
#: Integration roll-up), all built from the one ``threat_subject_ref`` convention.
THREAT_KINDS = (
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
)

#: The feed's display namespace for a threat item; the web strips it to sign off.
FEED_PREFIX = "threat:"


@pytest.fixture
def session() -> Iterator[Session]:
    engine_ = new_engine("sqlite://")
    Base.metadata.create_all(engine_)
    with new_session_factory(engine_)() as db:
        yield db


@pytest.fixture
def project(session: Session) -> Project:
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    session.add(project)
    session.commit()
    return project


def _overspend(session: Session) -> Project:
    """BAC 1000, EV 200 (20% done), AC 800 -> CPI 0.25: a red cost threat."""
    project = Project(
        name="Overspend",
        portfolio=Portfolio(name="P", business=Business(name="B")),
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


def test_threat_subject_ref_pins_the_canonical_format() -> None:
    assert threat_subject_ref("cost", 42) == "cost:project:42"
    assert threat_subject_ref("integration", 7) == "integration:project:7"


@pytest.mark.parametrize("kind", THREAT_KINDS)
def test_a_sign_off_via_the_builder_suppresses_that_kinds_threat(
    session: Session, project: Project, kind: str
) -> None:
    """Round-trip: builder -> threat.id -> feed display id -> web strip -> subject_ref -> suppress.

    Catches any prefix drift between the feed's display id and the suppression
    lookup: if the stripped subject_ref no longer byte-matches ``threat.id``, the
    sign-off stops suppressing and this fails.
    """
    ref = threat_subject_ref(kind, project.id)
    threat = Threat(ref, kind, "red", 1.0, f"{kind} threat", f"project:{project.id}")

    feed_item_id = f"{FEED_PREFIX}{ref}"  # what the feed emits for this threat
    subject_ref = feed_item_id.removeprefix(FEED_PREFIX)  # what the web signs off
    session.add(
        SignOff(
            project=project,
            subject_kind="threat",
            subject_ref=subject_ref,
            decision="accepted",
            signal=1.0,
        )
    )
    session.commit()
    assert engine.is_suppressed(session, threat, AS_OF)


def test_a_sign_off_for_another_kind_does_not_suppress(session: Session, project: Project) -> None:
    session.add(
        SignOff(
            project=project,
            subject_kind="threat",
            subject_ref=threat_subject_ref("schedule", project.id),
            decision="accepted",
            signal=1.0,
        )
    )
    session.commit()
    cost = Threat(
        threat_subject_ref("cost", project.id), "cost", "red", 1.0, "cost", f"project:{project.id}"
    )
    assert not engine.is_suppressed(session, cost, AS_OF)


def test_evaluators_id_their_threats_with_the_builder(session: Session) -> None:
    """The real evaluators (cost + the Integration roll-up) emit builder-formed ids."""
    project = _overspend(session)
    by_kind = {a.kind: a for a in engine.assess_project(session, project, AS_OF)}
    assert by_kind["cost"].threats[0].id == threat_subject_ref("cost", project.id)
    assert by_kind["integration"].threats[0].id == threat_subject_ref("integration", project.id)


def test_the_feed_round_trip_uses_the_builder(session: Session) -> None:
    """The feed's threat item id is the builder ref under the display prefix; a
    sign-off keyed off that stripped id removes the threat."""
    project = _overspend(session)
    top = feed.attention_feed(session, AS_OF)[0]
    ref = threat_subject_ref("cost", project.id)
    assert top.id == f"{FEED_PREFIX}{ref}"

    subject_ref = top.id.removeprefix(FEED_PREFIX)
    sign = SignOff(
        project=project, subject_kind="threat", subject_ref=subject_ref, decision="accepted"
    )
    sign.signal = top.score
    session.add(sign)
    session.commit()
    assert top.id not in [item.id for item in feed.attention_feed(session, AS_OF)]
