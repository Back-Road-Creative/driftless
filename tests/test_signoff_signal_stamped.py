"""The suppression signal is the score the server computed, never the one the caller posted.

Suppression is meant to be robust by construction: ``engine.is_suppressed`` hides a
signed-off threat only while its live score stays no worse than the ``signal`` recorded
at sign-off, so a regression past that level brings the threat straight back. That
guarantee rested entirely on ``signal`` being the score at the moment of sign-off — and
it was an ordinary request field. An authenticated caller could post ``signal=999`` (or
edit the hidden input the board renders) and mute that threat *permanently*: no real
score ever climbs past 999, so the re-arm the product promises silently never fires, on
an append-only row nobody can take back.

So the field is stamped, exactly as ``StatusSnapshot.percent_complete`` is stamped from
calc and ``SignOff.signed_by`` from the resolved principal: the server recomputes the
threat's score at the sign-off's own as-of and writes that. It is unreachable rather
than merely unused — the form handler no longer declares the parameter and ``SignOffIn``
no longer carries the field, so there is nothing left for a caller to influence.

A sign-off whose subject is not a currently-scored threat (a process decision, or a
threat that is not live at that as-of) records no signal at all, and a signal-less
sign-off never suppresses (``test_assess_engine`` pins that) — so a decision can never
pre-mute a threat that has not been assessed. Both write paths run through the real app.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.assess.feed import attention_feed
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
from driftless.web import csrf

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"
#: What a forged form or script posts to mute a threat for good — no score reaches it.
ABSURD = 999.0
COST = "cost:project:1"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    """One badly overspending project: BAC 1000, EV 200, AC 800 -> a red cost threat."""
    engine = new_engine(f"sqlite:///{tmp_path / 'signal.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as session:
        project = Project(
            name="GMS",
            portfolio=Portfolio(name="Content", business=Business(name="BRC")),
            delivery_mode="predictive",
        )
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
        session.add(CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
        session.commit()
    with factory() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def _live_score(db: Session, ref: str) -> float:
    """The score the board itself shows for ``ref`` at AS_OF — the feed, not a copy."""
    return next(item for item in attention_feed(db, AS_OF) if item.id == f"threat:{ref}").score


def _stored(db: Session) -> SignOff:
    db.expire_all()
    return db.scalars(select(SignOff)).one()


def _form(client: TestClient, **fields: str) -> dict[str, str]:
    client.get(f"/threats{Q}")  # the render that hands this browser its CSRF pair
    return {"as_of": AS_OF.isoformat(), csrf.FIELD: client.cookies[csrf.COOKIE], **fields}


def test_the_browser_form_stores_the_live_score_not_the_posted_signal(
    client: TestClient, db: Session
) -> None:
    live = _live_score(db, COST)
    assert live != ABSURD, "the seed must not coincidentally score what the forgery posts"

    posted = client.post(
        "/sign-off",
        data=_form(
            client,
            subject_kind="threat",
            subject_ref=COST,
            decision="accepted",
            signal=str(ABSURD),
            project_id="1",
        ),
        follow_redirects=False,
    )

    assert posted.status_code == 303, posted.text
    assert _stored(db).signal == pytest.approx(live), (
        "the hidden form input decided the suppression threshold — one edited field "
        "mutes a threat permanently and the re-arm never fires"
    )


def test_the_json_route_refuses_a_posted_signal(client: TestClient) -> None:
    """``signal`` is not a field of ``SignOffIn`` at all, and the request base now
    forbids any key it does not declare — so posting one is a 422 that never reaches
    the row, strictly stronger than the old guarantee of a 201 that silently discarded
    the claim. A caller who typo's a real field name gets the same protection."""
    rejected = client.post(
        "/sign-offs",
        json={
            "project_id": 1,
            "subject_kind": "threat",
            "subject_ref": COST,
            "decision": "accepted",
            "signal": ABSURD,
            "as_of": AS_OF.isoformat(),
        },
    )

    assert rejected.status_code == 422, rejected.text


def test_the_json_route_stores_the_live_score(client: TestClient, db: Session) -> None:
    """With no ``signal`` field left to post, the JSON route still lands the server's
    own computed score — the same guarantee the browser-form case above pins, proven
    here for the path a script or API client uses instead of the board."""
    live = _live_score(db, COST)

    created = client.post(
        "/sign-offs",
        json={
            "project_id": 1,
            "subject_kind": "threat",
            "subject_ref": COST,
            "decision": "accepted",
            "as_of": AS_OF.isoformat(),
        },
    )

    assert created.status_code == 201, created.text
    assert created.json()["signal"] == pytest.approx(live), "the response must not echo the claim"
    assert _stored(db).signal == pytest.approx(live)


def test_a_forged_signal_cannot_mute_a_worsening_threat(client: TestClient, db: Session) -> None:
    """The product promise, end to end: sign off at 999, then double the overrun."""
    client.post(
        "/sign-off",
        data=_form(
            client,
            subject_kind="threat",
            subject_ref=COST,
            decision="accepted",
            signal=str(ABSURD),
            project_id="1",
        ),
        follow_redirects=False,
    )
    assert COST not in client.get(f"/threats{Q}").text, "the accepted threat leaves the board"

    db.add(CostEntry(project_id=1, category="labour", incurred_on=JAN, amount=800.0))
    db.commit()

    assert COST in client.get(f"/threats{Q}").text, (
        "the overrun doubled and the threat stayed buried — suppression outlived the "
        "score it was signed off at"
    )


@pytest.mark.parametrize(
    ("kind", "ref", "decision"),
    [("process", "process:4.3:project:1", "waived"), ("threat", "risk:project:1", "accepted")],
)
def test_a_subject_with_no_live_score_records_no_signal(
    client: TestClient, db: Session, kind: str, ref: str, decision: str
) -> None:
    """A process decision has no score at all, and no risk threat is live at this as-of.

    Both store no signal — the process side exactly as it always did — and a
    signal-less sign-off never suppresses, so neither can pre-mute a future threat.
    """
    posted = client.post(
        "/sign-off",
        data=_form(
            client,
            subject_kind=kind,
            subject_ref=ref,
            decision=decision,
            signal=str(ABSURD),
            project_id="1",
        ),
        follow_redirects=False,
    )

    assert posted.status_code == 303, posted.text
    assert _stored(db).signal is None
