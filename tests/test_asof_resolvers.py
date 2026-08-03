"""Artifact resolvers answer for the as-of date asked, never for "now".

Every dated model the mapping layer reads — baselines (``approved_at``), change
requests and issues (``raised_on``), narrative artifacts (``updated_on``) — must
be invisible at an as-of before its stored date, or ``?as_of=`` time travel
fabricates history: a 2026 approval reads present in 2025 and completeness is
byte-identical at every date. The store under test is the demo seed posted
through the real validated API, so the filters are exercised through the same
rows the dashboard reads. The prefetch cache is covered too: a project outside
an open scope must raise, not read as empty ("nothing to assess" grades green).
"""

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.demo.cli import seed
from driftless.demo.data import ANCHOR, demo_payload
from driftless.pmbok import mapping, state

#: Pinned, long before any date the demo payload derives from its anchor.
LONG_BEFORE = date(2025, 1, 1)


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(real_app) as test_client:
            yield test_client
    finally:
        real_app.dependency_overrides.clear()


@pytest.fixture
def seeded(client: TestClient, db: Session) -> m.Project:
    """The demo store, walked through the real API; hands back the red project."""

    def post(path: str, body: dict[str, Any]) -> int:
        response = client.post(path, json=body)
        assert response.status_code == 201, response.text
        return int(response.json()["id"])

    def patch(path: str, body: dict[str, Any]) -> None:
        response = client.patch(path, json=body)
        assert response.status_code == 200, response.text

    seed(post, demo_payload(ANCHOR), patch)
    return db.scalars(select(m.Project).where(m.Project.name == "Season 4 Rollout")).one()


def test_completeness_is_lower_before_the_store_has_history(seeded: m.Project, db: Session) -> None:
    """The F-C4 proof: the same project, two as-ofs, two different figures —
    and every process produced solely by a dated artifact demotes with it."""
    early = state.completeness(seeded, db, LONG_BEFORE)
    now = state.completeness(seeded, db, ANCHOR)
    assert early is not None and now is not None
    assert early < now
    # 4.3 issue_log, 4.6 change_log, 5.4 scope_baseline, 6.6 schedule_baseline:
    # each has one required tracked output, and every one of those rows is dated
    # after LONG_BEFORE in the demo payload, so none may read PRODUCED there.
    at_now = {p.id: s for p, s in state.project_process_states(seeded, db, ANCHOR)}
    at_early = {p.id: s for p, s in state.project_process_states(seeded, db, LONG_BEFORE)}
    for pid in ("4.3", "4.6", "5.4", "6.6"):
        assert at_now[pid] is state.ProcessState.PRODUCED
        assert at_early[pid] is not state.ProcessState.PRODUCED


def test_baseline_kinds_wait_for_the_approval_date(seeded: m.Project, db: Session) -> None:
    baseline = db.scalars(select(m.Baseline).where(m.Baseline.project_id == seeded.id)).one()
    assert baseline.approved_at is not None  # the API's approval atomicity invariant
    approved = baseline.approved_at.date()
    for kind in ("scope_baseline", "schedule_baseline"):
        assert not mapping.resolve(kind, seeded, db, LONG_BEFORE).present
        assert not mapping.resolve(kind, seeded, db, approved - timedelta(days=1)).present
        assert mapping.resolve(kind, seeded, db, approved).present


def test_issue_log_waits_for_raised_on(seeded: m.Project, db: Session) -> None:
    issues = db.scalars(select(m.Issue).where(m.Issue.project_id == seeded.id)).all()
    raised = min(issue.raised_on for issue in issues)
    assert not mapping.resolve("issue_log", seeded, db, raised - timedelta(days=1)).present
    assert mapping.resolve("issue_log", seeded, db, raised).present


def test_change_log_waits_for_raised_on(seeded: m.Project, db: Session) -> None:
    changes = db.scalars(select(m.ChangeRequest).where(m.ChangeRequest.project_id == seeded.id))
    raised = min(change.raised_on for change in changes.all())
    assert not mapping.resolve("change_log", seeded, db, raised - timedelta(days=1)).present
    assert mapping.resolve("change_log", seeded, db, raised).present


def test_narrative_waits_for_updated_on_but_an_undated_row_counts(
    client: TestClient, seeded: m.Project, db: Session
) -> None:
    dated = {"project_id": seeded.id, "kind": "assumption_log", "body": "drone weather"}
    posted = client.post("/narrative-artifacts", json={**dated, "updated_on": ANCHOR.isoformat()})
    assert posted.status_code == 201, posted.text
    assert not mapping.resolve("assumption_log", seeded, db, LONG_BEFORE).present
    assert mapping.resolve("assumption_log", seeded, db, ANCHOR).present

    # The wizard files narratives without a date; an undated row must keep counting.
    undated = {"project_id": seeded.id, "kind": "eef", "body": "cloud-first"}
    assert client.post("/narrative-artifacts", json=undated).status_code == 201
    kind = "enterprise_environmental_factors"
    assert mapping.resolve(kind, seeded, db, LONG_BEFORE).present


def test_prefetch_scope_refuses_a_project_it_was_not_opened_for(
    seeded: m.Project, db: Session
) -> None:
    """The F-C12 proof: out of scope raises instead of failing open to "no rows"."""
    outsider = db.scalars(select(m.Project).where(m.Project.name == "Fleet Modernization")).one()
    with mapping.prefetched(db, [seeded]):
        assert mapping.resolve("risk_register", seeded, db, ANCHOR).present  # in scope: served
        with pytest.raises(LookupError, match="outside the open prefetched scope"):
            mapping.resolve("risk_register", outsider, db, ANCHOR)
