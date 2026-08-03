"""Two API-boundary guards, both about what a caller actually receives.

**The stamped percent honors the snapshot's own date.** ``stamped_percent`` used to
read earned value through ``gather.project_evm``, which holds no session and so reads
``Task.percent_complete`` — one undated *current* number that answers every as-of.
A weekly snapshot backdated to February therefore recorded TODAY's completion, and
because the status series is append-only (no PATCH or DELETE exists for it), the
wrong figure was permanent and the trend chart plotted it. The stamp now reads
through ``adapters.project_snapshot``, whose ChangeLog replay dates each progress
reading — so a backdated snapshot records what was true THEN.

**A constraint conflict answers in the surface's own language.** Refiling the weekly
status for an already-snapshotted date violates ``uq_status_snapshot_project_date``
inside the form handler — an everyday PM action — and the ``IntegrityError`` handler
answered raw JSON with no navigation, a dead end for a browser. The handler now asks
the same surface question every refusal in ``driftless.web.errors`` asks: a
page-surface request renders the designed HTML shell, and every API response stays
byte-for-byte what it was.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.models import (
    Baseline,
    BaselineLine,
    Business,
    Portfolio,
    Project,
    StatusSnapshot,
    Task,
    Workstream,
)
from driftless.web import csrf

JAN, BACKDATED, MAR = date(2026, 1, 1), date(2026, 2, 15), date(2026, 3, 31)


@pytest.fixture
def factory(tmp_path: Path) -> sessionmaker[Session]:
    """A changelog-registered factory over one baselined project entered at 20 percent.

    The listener is registered BEFORE the seed so the task's insert is logged — the
    undated reading that answers every as-of — exactly as any store written through
    the app's own factory would have it.
    """
    engine = new_engine(f"sqlite:///{tmp_path / 'guards.db'}")
    Base.metadata.create_all(engine)
    made = new_session_factory(engine)
    register_changelog(made)
    with made() as session:
        project = Project(
            name="GMS",
            portfolio=Portfolio(name="Content", business=Business(name="BRC")),
            delivery_mode="predictive",
        )
        stream = Workstream(name="Post", project=project)
        task = Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
        session.add(
            BaselineLine(
                baseline=Baseline(project=project, version=1, status="approved"),
                task=task,
                planned_cost=1000.0,
                planned_start=JAN,
                planned_finish=MAR,
            )
        )
        session.commit()
    return made


@pytest.fixture
def db(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app, base_url="https://testserver") as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def test_a_backdated_snapshot_stamps_the_percent_of_its_own_date(
    client: TestClient, db: Session
) -> None:
    """Raise the task to 80 today, then snapshot February 15: the series keeps 20.

    The raise goes through the app's own PATCH so the ChangeLog dates it — at
    today's UTC date, months after ``BACKDATED`` — and the insert reading of 20 is
    the dated truth for February. Stamping 80 onto the February row is permanent:
    the series has no PATCH or DELETE, and ``pages.trend_series`` plots it.
    """
    raised = client.patch("/tasks/1", json={"percent_complete": 80})
    assert raised.status_code == 200, raised.text

    created = client.post(
        "/status-snapshots",
        json={"project_id": 1, "taken_on": BACKDATED.isoformat(), "rag_status": "amber"},
    )

    assert created.status_code == 201, created.text
    assert created.json()["percent_complete"] == 20, (
        "the backdated snapshot recorded today's completion, not February's — and the "
        "append-only series makes that wrong figure permanent"
    )
    db.expire_all()
    stored = db.scalars(select(StatusSnapshot)).one()
    assert stored.percent_complete == 20


def test_a_duplicate_snapshot_date_still_answers_json_409_on_the_api(
    client: TestClient, db: Session
) -> None:
    """The API surface keeps its body byte-for-byte: JSON 409, never an HTML page."""
    body = {"project_id": 1, "taken_on": BACKDATED.isoformat(), "rag_status": "green"}
    assert client.post("/status-snapshots", json=body).status_code == 201, "first files fine"

    answer = client.post("/status-snapshots", json=body)

    assert answer.status_code == 409, answer.text
    assert answer.json() == {"detail": "constraint violation"}
    assert "text/html" not in answer.headers["content-type"]


def test_refiling_the_weekly_status_renders_the_html_conflict_page(
    client: TestClient, db: Session
) -> None:
    """The everyday trap: the form has no pre-check, so the second submit for the
    same date hits ``uq_status_snapshot_project_date`` — and the browser must get
    the designed shell with its navigation, not raw undressed JSON."""
    at = BACKDATED.isoformat()

    def form() -> dict[str, str]:
        client.get(f"/projects/1/status?as_of={at}")  # the render that mints the CSRF pair
        return {"as_of": at, "rag_status": "green", csrf.FIELD: client.cookies[csrf.COOKIE]}

    first = client.post("/projects/1/status", data=form(), follow_redirects=False)
    assert first.status_code == 303, first.text

    again = client.post("/projects/1/status", data=form(), follow_redirects=False)

    assert again.status_code == 409, again.text
    assert again.headers["content-type"].startswith("text/html"), (
        "a page-surface conflict answered raw JSON — no navigation, no way back"
    )
    assert "<nav" in again.text, "the conflict page must carry the shell's navigation"
    assert "constraint" not in again.text, "the page never echoes the database's wording"
