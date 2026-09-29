"""Contract tests for a couple of small display fixes:

- a RAID risk row's severity badge class is computed in ``raid_log.py``, not
  decided by the template;
- the method map's per-node panels use ``<h3>``, not one ``<h2>`` per node.
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
from driftless.models import (
    Baseline,
    BaselineLine,
    Business,
    CostEntry,
    Portfolio,
    Project,
    Risk,
    Task,
    Workstream,
)
from driftless.web.raid_log import _risk_severity

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"

HIGH_EXPOSURE_DESC = "Vendor default risk"
LOW_EXPOSURE_DESC = "Minor scheduling slip"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    with factory() as session:
        _seed(session)
    with factory() as session:
        yield session


def _seed(session: Session) -> Project:
    """One business, one project, carrying a high-exposure open risk
    (probability * impact >= 1000, the same threshold ``_risk_severity``
    reads) and a low-exposure one, so both severity bands render."""
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
    session.add(
        Risk(
            project=project,
            description=HIGH_EXPOSURE_DESC,
            probability=1.0,
            impact=2000.0,
            status="open",
            kind="threat",
        )
    )
    session.add(
        Risk(
            project=project,
            description=LOW_EXPOSURE_DESC,
            probability=0.1,
            impact=10.0,
            status="open",
            kind="threat",
        )
    )
    session.commit()
    return project


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def test_raid_severity_is_computed_not_rendered_from_a_template_expression(
    client: TestClient, db: Session
) -> None:
    project = db.query(Project).filter_by(name="GMS").one()
    page = client.get(f"/projects/{project.id}/raid{Q}").text
    high = db.query(Risk).filter_by(description=HIGH_EXPOSURE_DESC).one()
    low = db.query(Risk).filter_by(description=LOW_EXPOSURE_DESC).one()
    assert _risk_severity(high) == "sev-red"
    assert _risk_severity(low) == "sev-amber"
    # The rendered severity class matches what the router computed, row for row.
    # It sits on the cell; the badge inside carries the shared ``badge sev-badge``
    # fill (the ``.sev-red .sev-badge`` rule), like every other status pill.
    high_idx = page.index(HIGH_EXPOSURE_DESC)
    low_idx = page.index(LOW_EXPOSURE_DESC)
    badge = '<span class="badge sev-badge">'
    assert f'<td class="sev-red">{badge}' in page[high_idx : high_idx + 400]
    assert f'<td class="sev-amber">{badge}' in page[low_idx : low_idx + 400]


def test_the_method_map_does_not_drown_its_outline_in_per_node_headings(
    client: TestClient,
) -> None:
    page = client.get(f"/map{Q}").text
    assert page.count("<h2") <= 5
    assert "<h3>" in page


def test_a_pinned_as_of_renders_the_home_page_byte_identically(client: TestClient) -> None:
    assert client.get(f"/{Q}").text == client.get(f"/{Q}").text
