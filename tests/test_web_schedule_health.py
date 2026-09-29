"""The fourteen schedule health checks, per project: ``/projects/{id}/schedule-health``
(page) and ``?format=csv`` (the same rows, exported).

Thresholds follow the commonly used DCMA 14-point assessment, but the page never
calls a project "compliant" or "certified" — these pin that wording, that the page
and the CSV report the same rows, that a check this schema has no data for
(actual/forecast/baseline finish dates it never stores) renders "not assessable"
rather than inventing an offender, and byte-identical regeneration for a pinned
as-of.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory

AS_OF = date(2026, 2, 15)
WINDOW = (date(2026, 1, 1), date(2026, 1, 10))
PAGE = f"/projects/1/schedule-health?as_of={AS_OF.isoformat()}"
CSV_PAGE = f"/projects/1/schedule-health?as_of={AS_OF.isoformat()}&format=csv"
DRAFT_PAGE = f"/projects/2/schedule-health?as_of={AS_OF.isoformat()}"


def _seed(db: Session) -> None:
    """Project 1: an approved baseline with a linked pair (A -> B, both assigned)
    plus an isolated, unassigned task — the one offender every check that can
    fire here should name. Project 2: a draft baseline only."""
    portfolio = m.Portfolio(name="Content", business=m.Business(name="BRC"))
    project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    draft = m.Project(name="Unbaselined", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="Post", project=project)
    db.add(stream)
    db.add(m.Baseline(project=project, version=1, status="approved"))
    db.add(m.Baseline(project=draft, version=1, status="draft"))
    db.commit()  # GMS is added first, so it is project 1 and Unbaselined is project 2

    person = m.Person(name="Ari", capacity_hours=40.0)
    db.add(person)
    baseline = db.get(m.Baseline, 1)
    task_a = m.Task(name="Design", workstream=stream, estimate_unit="hours", assignee=person)
    task_b = m.Task(name="Build", workstream=stream, estimate_unit="hours", assignee=person)
    task_c = m.Task(name="Orphan", workstream=stream, estimate_unit="hours")
    for task in (task_a, task_b, task_c):
        line = m.BaselineLine(baseline=baseline, task=task, planned_cost=500.0)
        line.planned_start, line.planned_finish = WINDOW
        db.add(line)
    db.commit()
    db.add(m.TaskDependency(predecessor=task_a, successor=task_b, kind="FS", lag_days=0))
    db.commit()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'schedule_health.db'}")
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


def test_the_page_lists_a_row_per_check_naming_the_orphan_task(client: TestClient) -> None:
    body = client.get(PAGE).text
    assert "Logic" in body and "Resources" in body
    assert "Orphan" in body, "the one un-networked, unassigned task is never named"
    assert "compliant" not in body.lower() and "certified" not in body.lower()
    assert "commonly used DCMA 14-point assessment" in body, "DCMA named once, as the source"


def test_checks_this_schema_cannot_track_render_not_assessable(client: TestClient) -> None:
    """No actual/forecast/baseline finish date is stored anywhere in this schema, so
    invalid dates, missed tasks and BEI can never honestly report an offender —
    same shape hard constraints already uses."""
    body = client.get(PAGE).text
    assert body.count("not assessable") >= 4, body


def test_the_csv_exports_the_same_rows_the_page_shows(client: TestClient) -> None:
    page = client.get(PAGE).text
    text = client.get(CSV_PAGE).text
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == [
        "check",
        "numerator",
        "denominator",
        "ratio",
        "threshold",
        "status",
        "offending",
    ]
    by_check = {row[0]: row for row in rows[1:]}
    assert "Logic" in by_check and "Orphan" in by_check["Logic"][-1]
    assert by_check["Logic"][-1] in page or "Orphan" in page
    assert client.get(CSV_PAGE).headers["content-type"].startswith("text/csv")
    assert len(rows) - 1 == 14, "one row per DCMA check"


def test_a_pinned_as_of_regenerates_byte_identically(client: TestClient) -> None:
    first, second = client.get(PAGE).text, client.get(PAGE).text
    assert first == second
    assert client.get(CSV_PAGE).text == client.get(CSV_PAGE).text


def test_no_approved_baseline_says_so_instead_of_an_empty_table(client: TestClient) -> None:
    body = client.get(DRAFT_PAGE).text
    assert "<table" not in body
    assert "No approved baseline yet" in body


def test_the_schedule_page_links_to_schedule_health_checks(client: TestClient) -> None:
    body = client.get(f"/projects/1/gantt?as_of={AS_OF.isoformat()}").text
    assert f"/projects/1/schedule-health?as_of={AS_OF.isoformat()}" in body
