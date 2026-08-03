"""The risk threat score is ONE unit, whatever reserve a project holds.

The score used to switch units silently. With a reserve it was a ratio — the
shortfall as a share of contingency. With none, a ``max(contingency, 1.0)``
denominator floor turned it into raw dollars, and the two were then ranked
against each other on ``/threats``, the attention rail and ``assessment.md``:
a $600 uncovered exposure scored 600.0 and outranked a $45,000 one scoring 29.0.
Guarding the division was right; letting the guard change the unit was the bug.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.assess.evaluators import risk
from driftless.db import Base, new_engine, new_session_factory

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = new_engine("sqlite://")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as db:
        yield db


def _project(
    session: Session,
    name: str,
    *,
    bac: float,
    spent: float,
    reserve: float,
    exposure: float,
) -> m.Project:
    """A project with an approved plan worth ``bac`` running Jan–Mar, ``spent``
    against it, a ``contingency`` budget line of ``reserve`` (none when 0) and one
    open risk of ``exposure``. ``bac`` of 0 means nobody baselined it at all."""
    portfolio = m.Portfolio(name=f"PF-{name}", business=m.Business(name=f"B-{name}"))
    project = m.Project(name=name, portfolio=portfolio, delivery_mode="predictive")
    if bac:
        stream = m.Workstream(name="WS", project=project)
        task = m.Task(name="T", workstream=stream, estimate_unit="hours", percent_complete=0)
        session.add(
            m.BaselineLine(
                baseline=m.Baseline(project=project, version=1, status="approved"),
                task=task,
                planned_start=JAN,
                planned_finish=AS_OF,
                planned_cost=bac,
            )
        )
    if spent:
        session.add(m.CostEntry(project=project, category="labour", incurred_on=JAN, amount=spent))
    if reserve:
        session.add(m.BudgetLine(project=project, category="contingency", planned_amount=reserve))
    session.add(m.Risk(project=project, description=f"r-{name}", probability=1.0, impact=exposure))
    session.commit()
    return project


def _score(session: Session, project: m.Project) -> float:
    return risk.evaluate(session, project, AS_OF).risk_score


def test_a_bigger_uncovered_exposure_outranks_a_smaller_one(session: Session) -> None:
    """The measured inversion, in one store. Both are red; the small one holds no
    reserve at all, which is what used to switch its score into raw dollars."""
    big = _project(session, "Big", bac=15_000.0, spent=10_000.0, reserve=1_500.0, exposure=45_000.0)
    small = _project(session, "Small", bac=20_000.0, spent=0.0, reserve=0.0, exposure=600.0)
    assert risk.evaluate(session, big, AS_OF).status == "red"
    assert risk.evaluate(session, small, AS_OF).status == "red"
    assert _score(session, small) < _score(session, big), (
        "600 uncovered outranks 45,000 uncovered — the score is not one unit"
    )


@pytest.mark.parametrize("reserve", (0.0, 1_500.0), ids=("no-reserve", "with-reserve"))
def test_the_score_does_not_move_when_every_dollar_figure_scales(
    session: Session, reserve: float
) -> None:
    """The same project a thousand times bigger. A score in one unit is a share,
    so it cannot move; a score in dollars multiplies by a thousand."""
    small = _project(
        session, "Small", bac=20_000.0, spent=5_000.0, reserve=reserve, exposure=45_000.0
    )
    large = _project(
        session,
        "Large",
        bac=20_000_000.0,
        spent=5_000_000.0,
        reserve=reserve * 1_000,
        exposure=45_000_000.0,
    )
    assert _score(session, small) == _score(session, large)


def test_the_amber_score_is_the_overrun_past_the_half_reserve_line(session: Session) -> None:
    """Covered, but exposure has eaten past half the contingency: 3,000 against a
    5,000 reserve on a 20,000 budget scores (3,000 − 2,500) / 20,000 = 0.025.
    Pinned to the computed value — asserting only red and green left the amber
    formula free to return anything at all — and the threat must carry the same
    number, because it is what the ranked board sorts by."""
    thinning = _project(
        session, "Thinning", bac=20_000.0, spent=0.0, reserve=5_000.0, exposure=3_000.0
    )
    assessment = risk.evaluate(session, thinning, AS_OF)
    assert assessment.status == "amber"
    assert assessment.risk_score == 0.025
    assert assessment.threats[0].score == 0.025


def test_no_plan_is_no_basis_to_judge_rather_than_a_red(session: Session) -> None:
    """Nobody baselined it, so there is no budget, so no reserve, so nothing an
    open register can be weighed against. ``bac == 0`` is the "nothing to assess"
    signal the cost evaluator already answers green to; inventing a red out of it
    put a "no data" project at the top of the attention rail."""
    unplanned = _project(session, "Unplanned", bac=0.0, spent=0.0, reserve=0.0, exposure=600.0)
    assessment = risk.evaluate(session, unplanned, AS_OF)
    assert (assessment.status, assessment.risk_score, assessment.threats) == ("green", 0.0, ())


def test_an_as_of_before_the_plan_began_does_not_invent_a_red(session: Session) -> None:
    """Same root cause. Before the plan starts, ``adapters.snapshot_from`` refuses
    earned value, so BAC is 0 and the reserve reads 0 — a comfortably covered
    project must not flip red merely by being asked about an earlier date."""
    covered = _project(
        session, "Covered", bac=20_000.0, spent=0.0, reserve=5_000.0, exposure=1_000.0
    )
    assert risk.evaluate(session, covered, AS_OF).status == "green"
    before = risk.evaluate(session, covered, JAN - timedelta(days=1))
    assert (before.status, before.threats) == ("green", ())
