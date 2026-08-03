"""The attention feed: worst threat leads, sign-offs hold, incomplete-data
signals rank no_status > stale_status > low_completeness, staleness has a
14-day boundary, flagged items are wizard-enriched, and the order is byte-stable."""

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.assess import feed
from driftless.db import Base, new_engine, new_session_factory
from driftless.pmbok import catalog
from driftless.pmbok import mapping
from driftless.pmbok import state as st
from driftless.wizard import engine as wizard

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)


@pytest.fixture
def session() -> Iterator[Session]:
    engine_ = new_engine("sqlite://")
    Base.metadata.create_all(engine_)
    with new_session_factory(engine_)() as db:
        yield db


def _project(session: Session, name: str) -> m.Project:
    portfolio = m.Portfolio(name=f"P-{name}", business=m.Business(name=f"B-{name}"))
    project = m.Project(name=name, portfolio=portfolio, delivery_mode="predictive")
    session.add(project)
    session.commit()
    return project


def _overspend(session: Session) -> m.Project:
    """BAC 1000, EV 200 (20% done), AC 800 -> CPI 0.25: a red cost threat."""
    project = _project(session, "Overspend")
    stream = m.Workstream(name="Post", project=project)
    task = m.Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = m.Baseline(project=project, version=1, status="approved")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
    line.planned_start, line.planned_finish = JAN, AS_OF
    session.add(line)
    session.add(m.CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    session.commit()
    return project


def _snapshot(session: Session, project: m.Project, days_before: int) -> None:
    session.add(m.StatusSnapshot(project=project, taken_on=AS_OF - timedelta(days=days_before)))
    session.commit()


def _underfunded_risk(session: Session) -> m.Project:
    """A red risk threat scoring 0.05 -- below every data signal's fixed score.

    BAC 1000 with nothing spent leaves 1000 of budget, and no contingency budget
    line means none of it is held back: ANY open exposure is uncovered (red), and
    shortfall equals exposure exactly. A risk of probability 0.05 x impact 1000 is
    an exposure of 50 against 1000 remaining, pinning the threat's score to 0.05 --
    under the no_status signal's fixed 0.09 floor.

    It used to be seeded with no baseline at all, exposure 0.05 in dollars: the
    score then read 0.05 only because a zero reserve floored the denominator at $1
    and quietly made the score dollars. A project with no plan holds no reserve to
    fall short of, so it no longer raises a risk threat at all.
    """
    project = _project(session, "Underfunded")
    stream = m.Workstream(name="Post", project=project)
    task = m.Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=0)
    line = m.BaselineLine(baseline=m.Baseline(project=project, version=1, status="approved"))
    line.task, line.planned_cost = task, 1000.0
    line.planned_start, line.planned_finish = JAN, AS_OF
    session.add(line)
    session.add(m.Risk(project=project, description="small", probability=0.05, impact=1000.0))
    session.commit()
    return project


def test_stale_after_days_shares_the_cadence_constant() -> None:
    """Not a copy of ``mapping.STATUS_CADENCE_DAYS`` -- the SAME object, so
    loosening the cadence policy can't desync the feed's staleness read from
    the communications evaluator's."""
    assert feed.STALE_AFTER_DAYS is mapping.STATUS_CADENCE_DAYS


def test_a_red_threat_below_the_signal_floor_still_outranks_a_data_signal(
    session: Session,
) -> None:
    """Severity, not raw score, decides the threat/signal split: a red threat
    scoring 0.05 still leads a no_status signal fixed at 0.09."""
    underfunded = _underfunded_risk(session)
    silent = _project(session, "Silent")  # never filed a status -> no_status, 0.09

    items = feed.attention_feed(session, AS_OF)
    # Matched by id, not "first threat for this project" -- the project's own
    # missing status snapshot also fires an amber communications threat that
    # rolls up into a higher-scoring (but likewise red) integration threat, so
    # picking by id keeps this test pinned to the risk evaluator's own threat.
    risk_threat = next(i for i in items if i.id == f"threat:risk:project:{underfunded.id}")
    assert risk_threat.severity == "red"
    assert risk_threat.score == 0.05

    ids = [i.id for i in items]
    assert ids.index(risk_threat.id) < ids.index(f"no_status:project:{silent.id}")


def test_the_worst_threat_leads_and_a_sign_off_removes_it(session: Session) -> None:
    project = _overspend(session)
    first = feed.attention_feed(session, AS_OF)[0]
    assert first.kind == "threat" and first.severity == "red"
    assert first.id == f"threat:cost:project:{project.id}"
    assert first.project_name == "Overspend"

    ref = f"cost:project:{project.id}"
    sign = m.SignOff(project=project, subject_kind="threat", subject_ref=ref, decision="accepted")
    sign.signal = first.score
    session.add(sign)
    session.commit()
    assert f"threat:{ref}" not in [i.id for i in feed.attention_feed(session, AS_OF)]


def test_no_status_outranks_another_projects_low_completeness(session: Session) -> None:
    silent = _project(session, "Silent")  # never filed a status
    lagging = _project(session, "Lagging")
    _snapshot(session, lagging, 1)  # fresh, so only completeness flags it
    ids = [i.id for i in feed.attention_feed(session, AS_OF)]
    assert ids.index(f"no_status:project:{silent.id}") < ids.index(
        f"low_completeness:project:{lagging.id}"
    )


def test_stale_status_boundary_13_days_fresh_15_days_stale(session: Session) -> None:
    fresh, stale = _project(session, "Fresh"), _project(session, "Stale")
    _snapshot(session, fresh, 13)
    _snapshot(session, stale, 15)
    ids = [i.id for i in feed.attention_feed(session, AS_OF)]
    assert f"stale_status:project:{stale.id}" in ids
    assert f"stale_status:project:{fresh.id}" not in ids
    assert f"no_status:project:{fresh.id}" not in ids


def test_the_feed_is_deterministic_and_ties_break_by_id(session: Session) -> None:
    a, b = _project(session, "A"), _project(session, "B")
    first = feed.attention_feed(session, AS_OF)
    assert first == feed.attention_feed(session, AS_OF)
    ids = [i.id for i in first]
    # Both no_status items carry the same fixed score -> id ascending decides.
    assert ids.index(f"no_status:project:{a.id}") < ids.index(f"no_status:project:{b.id}")


def test_trend_delta_worsened_improved_unchanged_new() -> None:
    """Pure delta rule, matching ``web.pages._trend_delta`` bit for bit: rounded
    signed change drives up/down/flat, and no prior score reads 'new'."""
    assert feed.trend_delta(5.0, 3.0) == {"dir": "up", "amount": 2.0}
    assert feed.trend_delta(3.0, 5.0) == {"dir": "down", "amount": -2.0}
    assert feed.trend_delta(5.0, 5.0) == {"dir": "flat", "amount": 0.0}
    assert feed.trend_delta(5.0, None) == {"dir": "new", "amount": None}


def test_attention_trends_matches_worsening_and_new_by_id(session: Session) -> None:
    """Week-over-week compare, matched by item id -- same worked shape as the
    threat board's trend, applied to the whole attention feed (threats AND data
    signals). A fresh spend inside the last week widens an existing overspend
    (worsening); a second project's overspend begins entirely inside the last
    week, so it has no counterpart a week ago (new)."""
    worsening = _overspend(session)  # BAC 1000, AC 800 fully incurred back in JAN
    session.add(
        m.CostEntry(
            project=worsening,
            category="labour",
            incurred_on=AS_OF - timedelta(days=2),
            amount=200.0,
        )
    )
    fresh = _project(session, "Fresh")
    stream = m.Workstream(name="Post", project=fresh)
    task = m.Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = m.Baseline(project=fresh, version=1, status="approved")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
    line.planned_start, line.planned_finish = JAN, AS_OF
    session.add(line)
    session.add(
        m.CostEntry(
            project=fresh, category="labour", incurred_on=AS_OF - timedelta(days=2), amount=800.0
        )
    )
    session.commit()

    current = feed.attention_feed(session, AS_OF)
    trends = feed.attention_trends(session, AS_OF, current)

    worsened = next(i for i in current if i.project_id == worsening.id and i.kind == "threat")
    assert trends[worsened.id]["dir"] == "up"
    assert trends[worsened.id]["amount"] is not None and trends[worsened.id]["amount"] > 0

    new_item = next(i for i in current if i.project_id == fresh.id and i.kind == "threat")
    assert trends[new_item.id] == {"dir": "new", "amount": None}


def test_attention_trends_are_flat_for_an_unchanged_signal(session: Session) -> None:
    """A no_status signal carries a fixed score, so an unflagged week-over-week
    project reads flat, not up or down or new."""
    silent = _project(session, "Silent")
    current = feed.attention_feed(session, AS_OF)
    trends = feed.attention_trends(session, AS_OF, current)
    item = next(i for i in current if i.project_id == silent.id)
    assert trends[item.id] == {"dir": "flat", "amount": 0.0}


def test_attention_trends_never_reorders_the_feed(session: Session) -> None:
    """Trends annotate; ranking stays ``attention_feed``'s own order."""
    worsening = _overspend(session)
    session.add(
        m.CostEntry(
            project=worsening,
            category="labour",
            incurred_on=AS_OF - timedelta(days=2),
            amount=200.0,
        )
    )
    session.commit()
    current = feed.attention_feed(session, AS_OF)
    feed.attention_trends(session, AS_OF, current)
    assert [i.id for i in current] == [i.id for i in feed.attention_feed(session, AS_OF)]


def test_wizard_enrichment_on_flagged_and_silence_on_healthy(session: Session) -> None:
    healthy = _project(session, "Healthy")
    _snapshot(session, healthy, 1)
    quality = m.QualityMeasurement(project=healthy, metric="defects", target_value=5.0)
    quality.actual_value, quality.measured_on = 1.0, AS_OF - timedelta(days=5)
    session.add(quality)
    session.add_all(
        m.SignOff(
            project=healthy,
            subject_kind="process",
            subject_ref=st.process_subject_ref(process, healthy),
            decision="accepted",
        )
        for process in catalog.PROCESSES
        if st.is_assessable(process)
    )
    session.commit()
    flagged = _project(session, "Bare")

    items = feed.attention_feed(session, AS_OF)
    assert all(i.project_id != healthy.id for i in items), "a healthy project emits nothing"
    step = wizard.next_step(session, flagged, AS_OF)
    assert step is not None
    bare = next(i for i in items if i.id == f"no_status:project:{flagged.id}")
    assert step.name in bare.action, "the action names the wizard's next process"
