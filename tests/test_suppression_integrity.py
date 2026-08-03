"""Sign-off suppression in both directions: it hides a threat, and it lets go.

``driftless.assess.engine`` claims suppression is robust by construction — a
signed-off threat stays hidden only while its live score is no worse than the
score recorded at sign-off. The forward half (sign off, threat leaves) is the
easy half. What is pinned here is the half that decides whether suppression is
a decision or a permanent mute: when the underlying condition regresses PAST
the recorded signal, the threat comes back — on every surface an operator
reads, not just the per-threat predicate. That includes the store-wide
``top_threats`` walk, which answers suppression from a prefetched ledger cache
instead of the per-threat query, and the attention feed the web renders
verbatim. Without this, an operator who accepted one cost overrun would never
hear about the one twice its size.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.assess import engine, feed
from driftless.assess.model import Threat
from driftless.db import Base, new_engine, new_session_factory
from driftless.pmbok.state import threat_subject_ref

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)

#: The feed's display namespace over a threat's sign-off subject_ref.
FEED_PREFIX = "threat:"


@pytest.fixture
def session() -> Iterator[Session]:
    engine_ = new_engine("sqlite://")
    Base.metadata.create_all(engine_)
    with new_session_factory(engine_)() as db:
        yield db


def _overspend(session: Session, name: str = "Overspend") -> m.Project:
    """BAC 1000, EV 200 (20% done), AC 800 -> CPI 0.25: a red cost threat."""
    portfolio = m.Portfolio(name=f"P-{name}", business=m.Business(name=f"B-{name}"))
    project = m.Project(name=name, portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="Post", project=project)
    task = m.Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = m.Baseline(project=project, version=1, status="approved")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
    line.planned_start, line.planned_finish = JAN, AS_OF
    session.add(line)
    session.add(m.CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    session.commit()
    return project


def _regress(session: Session, project: m.Project) -> None:
    """Spend another 800 with nothing more earned — CPI 0.25 -> 0.125."""
    session.add(m.CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    session.commit()


def _sign_off(
    session: Session, project: m.Project, ref: str, signal: float | None, *, at: datetime
) -> None:
    session.add(
        m.SignOff(
            project=project,
            subject_kind="threat",
            subject_ref=ref,
            decision="accepted",
            signal=signal,
            signed_at=at,
        )
    )
    session.commit()


def _cost_threat(session: Session, project: m.Project) -> Threat:
    """The cost threat the evaluator computes, before any suppression is applied.

    Read from ``assess_project`` rather than a live feed on purpose: it is the
    ground truth a suppressed surface is measured against, so it stays readable
    while the threat is hidden.
    """
    by_kind = {a.kind: a for a in engine.assess_project(session, project, AS_OF)}
    return by_kind["cost"].threats[0]


def _surfaces(session: Session, project: m.Project, ref: str) -> dict[str, float | None]:
    """The cost threat's score on each surface an operator reads, or None if absent.

    ``live_threats`` answers suppression per threat; ``top_threats`` answers it
    from the store-wide prefetched sign-off cache; ``attention_feed`` is what the
    web renders. All three must agree, or suppression means different things in
    different places.
    """
    per_project = next(
        (t for t in engine.live_threats(session, project, AS_OF) if t.id == ref), None
    )
    store_wide = next((t for t in engine.top_threats(session, AS_OF) if t.id == ref), None)
    rendered = next(
        (i for i in feed.attention_feed(session, AS_OF) if i.id == f"{FEED_PREFIX}{ref}"), None
    )
    return {
        "live_threats": per_project.score if per_project else None,
        "top_threats": store_wide.score if store_wide else None,
        "attention_feed": rendered.score if rendered else None,
    }


def test_a_signed_off_threat_leaves_every_surface(session: Session) -> None:
    """Forward: sign off at the live score and the threat is gone from all three."""
    project = _overspend(session)
    ref = threat_subject_ref("cost", project.id)
    signed = _cost_threat(session, project)
    assert signed.severity == "red"
    assert _surfaces(session, project, ref) == {
        "live_threats": signed.score,
        "top_threats": signed.score,
        "attention_feed": signed.score,
    }

    _sign_off(session, project, ref, signed.score, at=datetime(2026, 2, 1, tzinfo=UTC))

    assert _surfaces(session, project, ref) == {
        "live_threats": None,
        "top_threats": None,
        "attention_feed": None,
    }


def test_a_regression_past_the_recorded_signal_returns_the_threat_everywhere(
    session: Session,
) -> None:
    """Reverse — the direction that makes suppression a decision, not a mute.

    An operator accepts the cost threat at CPI 0.25. Spend then doubles with
    nothing more earned (CPI 0.125), pushing the score past the recorded signal.
    The threat must come back on every surface, carrying the WORSE score — the
    number the operator has not seen — not the one they signed off.
    """
    project = _overspend(session)
    ref = threat_subject_ref("cost", project.id)
    signed_score = _cost_threat(session, project).score
    _sign_off(session, project, ref, signed_score, at=datetime(2026, 2, 1, tzinfo=UTC))
    assert _surfaces(session, project, ref)["top_threats"] is None, "suppressed to start with"

    _regress(session, project)

    worse = _cost_threat(session, project).score
    assert worse > signed_score, "the regression really did push the score past the signal"
    assert _surfaces(session, project, ref) == {
        "live_threats": worse,
        "top_threats": worse,
        "attention_feed": worse,
    }


def test_suppression_holds_at_the_recorded_signal_and_lifts_a_hair_past_it(
    session: Session,
) -> None:
    """The threshold is ``score <= signal``: equal stays hidden, any worse returns.

    Pinned on the boundary itself, so a comparison flipped to ``<`` (every
    unchanged threat re-surfacing) or to ``>=``-style leniency (a real
    regression staying hidden) both fail here.
    """
    project = _overspend(session)
    ref = threat_subject_ref("cost", project.id)
    threat = _cost_threat(session, project)

    _sign_off(session, project, ref, threat.score, at=datetime(2026, 2, 1, tzinfo=UTC))
    assert engine.is_suppressed(session, threat, AS_OF), "equal to the signal stays hidden"

    _sign_off(session, project, ref, threat.score - 0.0001, at=datetime(2026, 2, 2, tzinfo=UTC))
    assert not engine.is_suppressed(session, threat, AS_OF), "one step past the signal returns"


def test_a_fresh_sign_off_at_the_worse_score_re_suppresses(session: Session) -> None:
    """Suppression re-arms: acknowledging the regression quiets it again, at the new level."""
    project = _overspend(session)
    ref = threat_subject_ref("cost", project.id)
    _sign_off(
        session,
        project,
        ref,
        _cost_threat(session, project).score,
        at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    _regress(session, project)
    worse = _cost_threat(session, project).score

    _sign_off(session, project, ref, worse, at=datetime(2026, 3, 1, tzinfo=UTC))

    assert _surfaces(session, project, ref)["attention_feed"] is None


def test_a_sign_off_never_mutes_another_projects_threat(session: Session) -> None:
    """The store-wide pass caches every threat sign-off in one dict — keyed by a
    project-scoped subject_ref, so one project's decision cannot quiet another's."""
    signed, untouched = _overspend(session, "Signed"), _overspend(session, "Untouched")
    signed_ref = threat_subject_ref("cost", signed.id)
    other_ref = threat_subject_ref("cost", untouched.id)
    _sign_off(
        session,
        signed,
        signed_ref,
        _cost_threat(session, signed).score,
        at=datetime(2026, 2, 1, tzinfo=UTC),
    )

    ids = [t.id for t in engine.top_threats(session, AS_OF)]
    assert signed_ref not in ids
    assert other_ref in ids
