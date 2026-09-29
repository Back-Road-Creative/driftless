"""Unit tests for the RAID log surface (/projects/{project_id}/raid)."""

from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.models import Business, ChangeRequest, Issue, Portfolio, Project, Risk
import test_web_pages

client, db = test_web_pages.client, test_web_pages.db


def test_raid_log_empty_and_populated(client: TestClient, db: Session) -> None:
    seeded = db.scalars(select_project()).first()
    assert seeded is not None, (
        "the shared test_web_pages fixture seeds a project and this test covers the whole "
        "RAID-log surface against it. Skipping when it is absent would delete that coverage "
        "from a suite that still reports green, so a fixture that stops seeding must fail "
        "here instead."
    )

    # The empty state needs a project with NO risks -- the fixture's own project now
    # carries one (test_web_pages._seed, for the risk-response planner's own coverage),
    # so a second, otherwise-empty project is what actually proves "No risks registered"
    # still renders.
    project = Project(
        name="Blank",
        portfolio=Portfolio(name="P-Blank", business=Business(name="B-Blank")),
        delivery_mode="predictive",
    )
    db.add(project)
    db.commit()

    resp = client.get(f"/projects/{project.id}/raid")
    assert resp.status_code == 200
    assert "RAID Log" in resp.text
    assert "No risks registered" in resp.text

    risk = Risk(
        project_id=project.id,
        description="Budget overrun",
        probability=0.8,
        impact=500.0,
        response="mitigate",
        owner="Alice",
        status="open",
    )
    issue = Issue(
        project_id=project.id,
        description="Key vendor delayed",
        raised_on=date(2026, 1, 15),
        status="open",
    )
    change = ChangeRequest(
        project_id=project.id,
        description="Expand scope to mobile app",
        raised_on=date(2026, 2, 1),
        status="proposed",
    )
    db.add_all([risk, issue, change])
    db.commit()

    resp2 = client.get(f"/projects/{project.id}/raid")
    assert resp2.status_code == 200
    assert "Budget overrun" in resp2.text
    assert "Key vendor delayed" in resp2.text
    assert "Expand scope to mobile app" in resp2.text


def select_project():
    from sqlalchemy import select

    return select(Project)
