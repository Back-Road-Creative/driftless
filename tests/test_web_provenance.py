"""Provenance links: every computed figure on the weekly-status and project-hub
pages links to the rows it was computed from — the EVM figures to the CostEntry
rows AC is swept from, the trend/RAG to the StatusSnapshot rows it reads. Each
inputs page is read-only, computed, and renders no wall clock, so a pinned
as-of regenerates byte-identically.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.models import (
    Baseline,
    BaselineLine,
    Business,
    CostEntry,
    Portfolio,
    Project,
    StatusSnapshot,
    Task,
    Workstream,
)

JAN, FEB, MAR = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)
AS_OF = date(2026, 2, 15)
Q = f"?as_of={AS_OF.isoformat()}"


def _seed(session: Session) -> None:
    portfolio = Portfolio(name="Content", business=Business(name="BRC"))
    project = Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=40)
    baseline = Baseline(project=project, version=1, status="approved")
    line = BaselineLine(
        baseline=baseline, task=task, planned_cost=1000.0, planned_start=JAN, planned_finish=MAR
    )
    session.add(line)
    # Two costs on/before AS_OF (feed AC), one after (must NOT feed it).
    session.add(CostEntry(project=project, category="labour", incurred_on=JAN, amount=200.0))
    session.add(CostEntry(project=project, category="labour", incurred_on=FEB, amount=100.0))
    session.add(CostEntry(project=project, category="labour", incurred_on=MAR, amount=999.0))
    # Two snapshots — the trend query carries no as_of bound, so both feed it,
    # including the one recorded after AS_OF.
    session.add(
        StatusSnapshot(project=project, taken_on=JAN, percent_complete=10, rag_status="green")
    )
    session.add(
        StatusSnapshot(project=project, taken_on=MAR, percent_complete=40, rag_status="amber")
    )
    session.commit()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as session:
        _seed(session)
    with factory() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app) as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def test_status_page_links_to_its_snapshot_inputs(client: TestClient) -> None:
    body = client.get(f"/projects/1/status{Q}").text
    assert f'href="/projects/1/status/inputs?as_of={AS_OF.isoformat()}"' in body


def test_status_page_links_to_its_cost_inputs(client: TestClient) -> None:
    body = client.get(f"/projects/1/status{Q}").text
    assert f'href="/projects/1/hub/costs?as_of={AS_OF.isoformat()}"' in body


def test_hub_page_links_to_its_cost_inputs(client: TestClient) -> None:
    body = client.get(f"/projects/1/hub{Q}").text
    assert f'href="/projects/1/hub/costs?as_of={AS_OF.isoformat()}"' in body


def test_status_inputs_lists_exactly_the_rows_the_trend_reads(
    client: TestClient, db: Session
) -> None:
    """The trend query (``status_form``) carries no ``taken_on`` bound, so the
    inputs page must list every snapshot — including the one recorded after
    the page's own as-of — never a filtered subset that would disagree with
    the chart it documents."""
    body = client.get(f"/projects/1/status/inputs{Q}").text
    snapshots = db.query(StatusSnapshot).order_by(StatusSnapshot.id).all()
    assert len(snapshots) == 2
    for snap in snapshots:
        assert f"<td>{snap.id}</td>" in body
        assert f"<td>{snap.taken_on.isoformat()}</td>" in body
    assert body.count("<tr><td>") == 2


def test_hub_costs_lists_exactly_the_rows_ac_is_swept_from(client: TestClient, db: Session) -> None:
    """AC filters ``incurred_on <= as_of`` (``calc.evm.actual_cost``); the March
    entry (after AS_OF) must be excluded, matching what the EV/CPI/SPI figures
    actually summed."""
    body = client.get(f"/projects/1/hub/costs{Q}").text
    assert "<td>200" in body or "$200" in body
    assert "999" not in body, "a cost entry posted after as-of must not appear"
    assert body.count("<tr><td>") == 2


def test_a_pinned_as_of_regenerates_the_inputs_pages_byte_identically(
    client: TestClient,
) -> None:
    for url in (f"/projects/1/status/inputs{Q}", f"/projects/1/hub/costs{Q}"):
        assert client.get(url).content == client.get(url).content
