"""``GET /projects/{id}/baselines/diff`` — the per-line delta between two
approved baseline versions, read-only and computed. With no ``versions`` query
param it defaults to the two most recent approved baselines; ``?versions=v1...v2``
names an explicit pair. No SignOff column: each baseline's own approval
(status, approved_at) stands in, plus the change request that produced the
later version, when one exists.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory

JAN, FEB, MAR = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)
PAGE = "/projects/1/baselines/diff?versions=1...2"


def _seed(db: Session) -> None:
    """v1 (approved): one task, Design. v2 (approved, via a change request): Design
    slips and costs more, Build is new. Kept unbaselined: v3, a draft — the
    unapproved-endpoint 404 case."""
    portfolio = m.Portfolio(name="Content", business=m.Business(name="BRC"))
    project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="Post", project=project)
    design = m.Task(name="Design", workstream=stream, estimate_unit="hours")
    build = m.Task(name="Build", workstream=stream, estimate_unit="hours")
    v1 = m.Baseline(project=project, version=1, status="approved", approved_at=datetime(2026, 1, 1))
    line1 = m.BaselineLine(baseline=v1, task=design, planned_cost=1000.0)
    line1.planned_start, line1.planned_finish = JAN, FEB
    v2 = m.Baseline(project=project, version=2, status="approved", approved_at=datetime(2026, 2, 1))
    change = m.ChangeRequest(
        project=project,
        description="Slip Design, add Build",
        raised_on=JAN,
        status="approved",
        resulting_baseline=v2,
    )
    line2 = m.BaselineLine(baseline=v2, task=design, planned_cost=1500.0)
    line2.planned_start, line2.planned_finish = FEB, MAR
    line3 = m.BaselineLine(baseline=v2, task=build, planned_cost=750.0)
    line3.planned_start, line3.planned_finish = FEB, MAR
    db.add_all([line1, line2, line3, change])
    db.add(m.Baseline(project=project, version=3, status="draft"))
    db.commit()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'baseline_diff.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        _seed(session)
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as browser:
        yield browser
    real_app.dependency_overrides.clear()


def test_the_diff_page_shows_each_lines_delta_and_the_approvals(client: TestClient) -> None:
    body = client.get(PAGE).text
    assert "Design" in body and "Build" in body
    assert "1000.0" in body and "1500.0" in body, "Design's before/after cost is not shown"
    assert "added" in body, "Build, new in v2, is not marked added"
    assert "changed" in body, "Design, changed in v2, is not marked changed"
    assert "approved" in body
    assert "Slip Design, add Build" in body, "the change request that produced v2 is not named"
    assert "Sign-off" not in body and "SignOff" not in body


def test_with_no_versions_given_it_defaults_to_the_two_most_recent_approved(
    client: TestClient,
) -> None:
    body = client.get("/projects/1/baselines/diff").text
    assert "v1" in body and "v2" in body
    assert "Slip Design, add Build" in body


def test_an_unapproved_baseline_is_404(client: TestClient) -> None:
    assert client.get("/projects/1/baselines/diff?versions=1...3").status_code == 404


def test_an_unknown_baseline_version_is_404(client: TestClient) -> None:
    assert client.get("/projects/1/baselines/diff?versions=1...99").status_code == 404


def test_a_malformed_version_pair_is_404(client: TestClient) -> None:
    assert client.get("/projects/1/baselines/diff?versions=abc...def").status_code == 404


def test_fewer_than_two_approved_baselines_renders_its_own_empty_state(
    client: TestClient, db: Session
) -> None:
    """Nothing named is wrong here — there is no unknown or unapproved baseline, just
    not yet a second approved one to default a diff to — so this is a page state
    (200), not the "unknown/unapproved baseline" 404 the other cases above raise."""
    portfolio = m.Portfolio(name="Solo portfolio", business=m.Business(name="Solo biz"))
    project = m.Project(name="Solo", portfolio=portfolio, delivery_mode="predictive")
    db.add(
        m.Baseline(project=project, version=1, status="approved", approved_at=datetime(2026, 1, 1))
    )
    db.commit()
    page = client.get(f"/projects/{project.id}/baselines/diff")
    assert page.status_code == 200
    assert "Fewer than two approved baselines" in page.text
